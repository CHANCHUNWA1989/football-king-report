"""Offline fixture-to-private-quote binding: no API keys, credits or real prices."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from private_quote_snapshot_receipt import create_receipt
from private_quote_fixture_binding import BindingError, bind_private_fixture

CAPTURE = "2026-11-02T05:00:00Z"


def dataset():
    event = {
        "id": "native-event-A", "sport_key": "soccer_epl",
        "home_team": "Private Home", "away_team": "Private Away",
        "commence_time": "2026-11-02T08:00:00Z",
        "bookmakers": [{
            "key": "book-one",
            "markets": [
                {"key": "h2h", "last_update": "2026-11-02T04:59:30Z",
                 "outcomes": [
                     {"name": "Private Home", "price": 2.12},
                     {"name": "Draw", "price": 3.46},
                     {"name": "Private Away", "price": 4.56}]},
                {"key": "spreads", "last_update": "2026-11-02T04:59:30Z",
                 "outcomes": [
                     {"name": "Private Home", "price": 1.95, "point": -0.25},
                     {"name": "Private Away", "price": 1.91, "point": 0.25}]},
                {"key": "totals", "last_update": "2026-11-02T04:59:30Z",
                 "outcomes": [
                     {"name": "Over", "price": 1.92, "point": 2.75},
                     {"name": "Under", "price": 1.96, "point": 2.75}]},
            ]
        }]
    }
    return [event]


def fixture():
    return {"provider_event_id": "native-event-A", "sport_key": "soccer_epl",
            "home_team": "Private Home", "away_team": "Private Away",
            "kickoff_utc": "2026-11-02T08:00:00Z"}


def raw(items):
    return json.dumps(items, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def run(items, *, binding=None, market=None):
    data = raw(items)
    receipt = create_receipt(data, CAPTURE)
    return bind_private_fixture(
        data, receipt, fixture() if binding is None else binding,
        {"market_type": "totals", "goals_line": 2.75} if market is None else market)


class PrivateQuoteFixtureBindingTests(unittest.TestCase):
    def test_exact_event_id_and_quarter_totals_complete(self):
        report = run(dataset())
        self.assertEqual(report["status"], "RESEARCH_ONLY")
        self.assertEqual(report["market_type_requested"], "totals")
        self.assertEqual(report["atomic_bookmaker_groups_for_requested_line"], 1)
        self.assertTrue(report["requested_line_structurally_observed"])
        self.assertTrue(report["raw_snapshot_digest_replayed"])
        self.assertTrue(report["caller_fixture_matched_exact_native_id_and_kickoff"])
        for item in ("cross_provider_fixture_id_authenticated",
                     "fixture_assertion_independently_authenticated",
                     "quote_source_independently_authenticated",
                     "quote_capture_clock_independently_authenticated",
                     "executable_bookmaker_quote_verified",
                     "independent_model_ev_verified",
                     "eligible_for_betting_promotion"):
            self.assertIs(report[item], False, item)
        self.assertEqual(report["production_recommendations"], "DISABLED")
        safe = json.dumps(report)
        for private in ("native-event-A", "Private Home", "Private Away",
                        "book-one", "1.92", "1.95", "2.75"):
            self.assertNotIn(private, safe)

    def test_expected_spread_signed_home_quarter_line(self):
        good = run(dataset(), market={"market_type": "spreads", "home_line": -0.25})
        self.assertEqual(good["atomic_bookmaker_groups_for_requested_line"], 1)
        wrong = run(dataset(), market={"market_type": "spreads", "home_line": 0.25})
        self.assertEqual(wrong["atomic_bookmaker_groups_for_requested_line"], 0)
        self.assertEqual(wrong["status"], "HOLD")

    def test_h2h_requires_three_sides(self):
        market = {"market_type": "h2h"}
        self.assertEqual(run(dataset(), market=market)["atomic_bookmaker_groups_for_requested_line"], 1)
        one = dataset()
        one[0]["bookmakers"][0]["markets"][0]["outcomes"].pop()
        self.assertEqual(run(one, market=market)["status"], "HOLD")

    def test_offset_aware_same_kickoff_matches_without_rounding(self):
        value = fixture()
        value["kickoff_utc"] = "2026-11-02T16:00:00+08:00"
        self.assertTrue(run(dataset(), binding=value)["requested_line_structurally_observed"])
        value["kickoff_utc"] = "2026-11-02T08:00:00.000001Z"
        with self.assertRaisesRegex(BindingError, "FIXTURE_KICKOFF_MISMATCH"):
            run(dataset(), binding=value)

    def test_wrong_native_event_id_cannot_inherit_other_match_odds(self):
        for field, value in (
            ("provider_event_id", "native-event-B"),
            ("sport_key", "soccer_spain_la_liga"),
            ("home_team", "Different Home"),
            ("away_team", "Different Away"),
        ):
            with self.subTest(field=field):
                bad = dict(fixture(), **{field: value})
                with self.assertRaises(BindingError):
                    run(dataset(), binding=bad)

    def test_same_fixture_names_cannot_replace_source_native_event_id(self):
        items = dataset()
        other = copy.deepcopy(items[0])
        other["id"] = "native-event-B"
        items.append(other)
        bad = dict(fixture(), provider_event_id="native-event-B")
        result = run(items, binding=bad)
        self.assertEqual(result["atomic_bookmaker_groups_for_requested_line"], 1)
        self.assertFalse(result["cross_provider_fixture_id_authenticated"])
        # This is exact native ID matching only, not verified same-game crosswalk.

    def test_duplicate_native_id_quarantines_every_copy(self):
        rows = dataset()
        rows.append(copy.deepcopy(rows[0]))
        data = raw(rows)
        receipt = create_receipt(data, CAPTURE)
        with self.assertRaisesRegex(BindingError, "MISSING_OR_AMBIGUOUS_NATIVE_EVENT_ID"):
            bind_private_fixture(data, receipt, fixture(),
                                 {"market_type": "totals", "goals_line": 2.75})

    def test_no_cross_bookmaker_half_quote_pairing(self):
        rows = dataset()
        book = rows[0]["bookmakers"][0]
        total = book["markets"][2]
        over, under = total["outcomes"]
        book["markets"].pop(2)
        book["markets"].append(dict(total, outcomes=[over]))
        rows[0]["bookmakers"].append({
            "key": "book-two", "markets": [dict(total, outcomes=[under])]})
        result = run(rows)
        self.assertEqual(result["atomic_bookmaker_groups_for_requested_line"], 0)
        self.assertEqual(result["status"], "HOLD")

    def test_wrong_line_and_mismatched_line_hold(self):
        self.assertEqual(run(dataset(), market={"market_type": "totals",
                                                 "goals_line": 2.5})["status"], "HOLD")
        rows = dataset()
        rows[0]["bookmakers"][0]["markets"][2]["outcomes"][1]["point"] = 2.5
        self.assertEqual(run(rows)["status"], "HOLD")

    def test_expired_future_and_inplay_quotes_do_not_validate(self):
        for label in ("stale", "future", "inplay"):
            with self.subTest(label=label):
                rows = dataset()
                if label == "stale":
                    rows[0]["bookmakers"][0]["markets"][2]["last_update"] = "2026-11-02T04:55:00Z"
                elif label == "future":
                    rows[0]["bookmakers"][0]["markets"][2]["last_update"] = "2026-11-02T05:00:09Z"
                else:
                    rows[0]["commence_time"] = "2026-11-02T04:45:00Z"
                    expected = dict(fixture(), kickoff_utc="2026-11-02T04:45:00Z")
                result = run(rows, binding=expected if label == "inplay" else fixture())
                self.assertEqual(result["status"], "HOLD")

    def test_different_market_timestamp_or_duplicate_bookmarket_cannot_join(self):
        rows = dataset()
        market = rows[0]["bookmakers"][0]["markets"][2]
        over, under = market["outcomes"]
        rows[0]["bookmakers"][0]["markets"][2:3] = [
            dict(market, outcomes=[over]),
            dict(market, last_update="2026-11-02T04:59:29Z", outcomes=[under])]
        self.assertEqual(run(rows)["status"], "HOLD")

    def test_tampered_raw_bytes_or_forged_replay_receipt_blocked(self):
        data = raw(dataset())
        receipt = create_receipt(data, CAPTURE)
        with self.assertRaisesRegex(BindingError, "PRIVATE_RECEIPT_REPLAY_FAILED"):
            bind_private_fixture(data + b" ", receipt, fixture(),
                                 {"market_type": "totals", "goals_line": 2.75})
        forged = dict(receipt, publisher_independently_authenticated=True)
        with self.assertRaisesRegex(BindingError, "PRIVATE_RECEIPT_REPLAY_FAILED"):
            bind_private_fixture(data, forged, fixture(),
                                 {"market_type": "totals", "goals_line": 2.75})

    def test_boolean_nonquarter_bad_market_and_bad_fixture_fail_closed(self):
        for market in (
            {"market_type": "totals", "goals_line": 2.6},
            {"market_type": "totals", "goals_line": True},
            {"market_type": "spreads", "home_line": float("nan")},
            {"market_type": "h2h", "goals_line": 2.75},
            {"market_type": "unknown"},
            {"market_type": []},
            {"market_type": "totals", "goals_line": -0.25},
        ):
            with self.subTest(market=repr(market)):
                with self.assertRaises(BindingError):
                    run(dataset(), market=market)
        for bad in (
            dict(fixture(), provider_event_id=" "),
            dict(fixture(), home_team="Private Away"),
            dict(fixture(), kickoff_utc="2026-11-02T08:00:00"),
            dict(fixture(), stray_public_key="x"),
        ):
            with self.subTest(fixture=repr(bad)):
                with self.assertRaises(BindingError):
                    run(dataset(), binding=bad)

    def test_input_payload_and_binding_are_not_modified(self):
        rows = dataset()
        before = copy.deepcopy(rows)
        binding = fixture()
        market = {"market_type": "totals", "goals_line": 2.75}
        raw_bytes = raw(rows)
        receipt = create_receipt(raw_bytes, CAPTURE)
        receipt_before = copy.deepcopy(receipt)
        result = bind_private_fixture(raw_bytes, receipt, binding, market)
        self.assertTrue(result["requested_line_structurally_observed"])
        self.assertEqual(rows, before)
        self.assertEqual(receipt, receipt_before)
        self.assertEqual(binding, fixture())
        self.assertEqual(market, {"market_type": "totals", "goals_line": 2.75})


if __name__ == "__main__":
    unittest.main()
