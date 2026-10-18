import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_quote_gate import extract

NOW="2026-10-09T14:00:00Z"
def event():
    return [{"id":"fixture1","sport_key":"soccer_epl",
        "commence_time":"2026-10-09T13:00:00Z",
        "home_team":"Home","away_team":"Away",
        "bookmakers":[{"key":"sample","last_update":"2026-10-09T14:00:00Z",
            "markets":[{"key":"totals","last_update":"2026-10-09T13:59:30Z",
                "outcomes":[{"name":"Under","price":1.74,"point":1.75},
                            {"name":"Over","price":2.06,"point":1.75}]},
                       {"key":"spreads","last_update":"2026-10-09T13:59:20Z",
                "outcomes":[{"name":"Home","price":1.88,"point":0.25},
                            {"name":"Away","price":1.99,"point":-0.25}]},
                       {"key":"h2h","last_update":"2026-10-09T13:59:45Z",
                "outcomes":[{"name":"Home","price":2.2},
                            {"name":"Draw","price":3.1},
                            {"name":"Away","price":3.4}]}]}]}]

def run(payload):
    return extract(payload,captured_utc=NOW,league="soccer_epl",
                   home="Home",away="Away")

class QuoteGateTests(unittest.TestCase):
    def test_seven_quotes_across_three_markets(self):
        result=run(event())
        self.assertEqual(result["quotes_accepted"],7)
        self.assertEqual(result["status"],"RESEARCH_ONLY")
        self.assertFalse(result["executable_bookmaker_price_verified"])
        self.assertIsNone(result["recommendation"])
        self.assertEqual(result["production_recommendations"],"DISABLED")
        self.assertTrue(all(x["status"]=="FRESH_OBSERVATION_NOT_EXECUTABLE"
                            for x in result["quotes"]))

    def test_inplay_quotes_are_explicitly_labeled_not_prematch(self):
        result=run(event())
        self.assertEqual(result["pre_match_quote_observations"],0)
        self.assertEqual(result["in_play_or_too_late_quote_observations"],7)
        self.assertTrue(all(x["market_phase_at_capture"]=="IN_PLAY_OR_TOO_LATE"
                            and x["quote_pre_match_at_capture"] is False
                            for x in result["quotes"]))
        self.assertFalse(result["executable_bookmaker_price_verified"])

    def test_true_prematch_quotes_not_confused_with_inplay(self):
        events=event()
        events[0]["commence_time"]="2026-10-09T18:00:00Z"
        result=run(events)
        self.assertEqual(result["pre_match_quote_observations"],7)
        self.assertEqual(result["in_play_or_too_late_quote_observations"],0)
        self.assertTrue(all(x["market_phase_at_capture"]=="PREMATCH"
                            and x["quote_pre_match_at_capture"] is True
                            for x in result["quotes"]))
        self.assertFalse(result["quote_origin_does_not_prove_executability"] is False)

    def test_post_kickoff_quote_not_prematch_evidence(self):
        result=run(event())
        self.assertEqual(result["quotes_accepted"],7)
        self.assertTrue(all(not q["quote_updated_before_kickoff"] for q in result["quotes"]))
        self.assertTrue(all(not q["quote_eligible_as_prematch_evidence"] for q in result["quotes"]))
        self.assertFalse(result["executable_bookmaker_price_verified"])

    def test_pre_kickoff_update_and_capture_required(self):
        d=event()
        d[0]["commence_time"]="2026-10-09T18:00:00Z"
        result=run(d)
        self.assertEqual(result["quotes_accepted"],7)
        self.assertTrue(all(q["quote_eligible_as_prematch_evidence"] for q in result["quotes"]))
        self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_market_timestamp_missing_rejects_even_if_bookmaker_recent(self):
        d=event()
        del d[0]["bookmakers"][0]["markets"][0]["last_update"]
        result=run(d)
        self.assertEqual(result["quotes_accepted"],5)
        self.assertEqual(result["reject_reasons"]["MISSING_MARKET_LAST_UPDATE"],1)

    def test_old_market_time_rejects(self):
        d=event()
        d[0]["bookmakers"][0]["markets"][0]["last_update"]="2026-10-09T13:40:00Z"
        self.assertEqual(run(d)["reject_reasons"]["STALE_OR_FUTURE_MARKET"],1)

    def test_future_market_clock_rejects(self):
        d=event()
        d[0]["bookmakers"][0]["markets"][0]["last_update"]="2026-10-09T14:03:00Z"
        self.assertEqual(run(d)["quotes_accepted"],5)

    def test_invalid_price_boolean_and_nan_rejected(self):
        d=event()
        d[0]["bookmakers"][0]["markets"][0]["outcomes"][0]["price"]=True
        d[0]["bookmakers"][0]["markets"][0]["outcomes"][1]["price"]=float("nan")
        result=run(d)
        self.assertEqual(result["quotes_accepted"],5)
        self.assertEqual(result["reject_reasons"]["INVALID_DECIMAL_PRICE"],2)

    def test_invalid_quarter_line_rejected(self):
        d=event()
        d[0]["bookmakers"][0]["markets"][0]["outcomes"][0]["point"]=1.33
        self.assertEqual(run(d)["reject_reasons"]["INVALID_ASIAN_POINT"],1)

    def test_corroborrated_cross_bookmaker_price_outlier_is_research_only(self):
        d=event()
        d[0]["commence_time"]="2026-10-09T18:00:00Z"
        for key,price in (("book_b",1.79),("book_c",20.0)):
            book=copy.deepcopy(d[0]["bookmakers"][0])
            book["key"]=key
            book["markets"][0]["outcomes"][0]["price"]=price
            d[0]["bookmakers"].append(book)
        result=run(d)
        flagged=[q for q in result["quotes"] if q["cross_bookmaker_price_outlier"]]
        self.assertEqual(len(flagged),1)
        self.assertEqual(result["cross_bookmaker_price_outliers"],1)
        self.assertEqual(flagged[0]["bookmaker"],"book_c")
        self.assertFalse(flagged[0]["quote_eligible_as_prematch_evidence"])
        self.assertEqual(result["quotes_accepted"],21)
        self.assertEqual(result["production_recommendations"],"DISABLED")
        d[0]["bookmakers"].reverse()
        again=run(d)
        self.assertEqual([q["bookmaker"] for q in again["quotes"]
                          if q["cross_bookmaker_price_outlier"]],["book_c"])

    def test_inplay_quotes_do_not_corroborrate_prematch_outlier(self):
        d=event()
        d[0]["commence_time"]="2026-10-09T18:00:00Z"
        for key,price in (("book_b",1.79),("book_c",20.0)):
            book=copy.deepcopy(d[0]["bookmakers"][0])
            book["key"]=key
            book["markets"][0]["outcomes"][0]["price"]=price
            d[0]["bookmakers"].append(book)
        # The third bookmaker's timestamp is after kickoff. It remains
        # a research observation, but cannot corroborate prematch odds.
        d[0]["bookmakers"][1]["markets"][0]["last_update"]="2026-10-09T18:01:00Z"
        # A timestamp after kickoff is also beyond capture freshness, so
        # this bookmaker is rejected before outlier detection.
        result=run(d)
        self.assertEqual(result["cross_bookmaker_price_outliers"],0)
        self.assertEqual(result["reject_reasons"]["STALE_OR_FUTURE_MARKET"],1)
        self.assertEqual(result["quotes_accepted"],19)
        self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_inplay_snapshot_cannot_claim_corroborrated_price_outlier(self):
        d=event()
        for key,price in (("book_b",1.79),("book_c",20.0)):
            book=copy.deepcopy(d[0]["bookmakers"][0])
            book["key"]=key
            book["markets"][0]["outcomes"][0]["price"]=price
            d[0]["bookmakers"].append(book)
        result=run(d)
        self.assertEqual(result["quotes_accepted"],21)
        self.assertEqual(result["cross_bookmaker_price_outliers"],0)
        self.assertTrue(all(not q["quote_eligible_as_prematch_evidence"]
                            for q in result["quotes"]))

    def test_noncontemporaneous_bookmaker_quotes_not_used_for_outliers(self):
        d=event()
        d[0]["commence_time"]="2026-10-09T18:00:00Z"
        for key,price in (("book_b",1.79),("book_c",20.0)):
            book=copy.deepcopy(d[0]["bookmakers"][0])
            book["key"]=key
            book["markets"][0]["outcomes"][0]["price"]=price
            d[0]["bookmakers"].append(book)
        d[0]["bookmakers"][2]["markets"][0]["last_update"]="2026-10-09T13:58:45Z"
        result=run(d)
        self.assertEqual(result["quotes_accepted"],21)
        self.assertEqual(result["cross_bookmaker_price_outliers"],0)
        self.assertTrue(all(q["quote_eligible_as_prematch_evidence"]
                            for q in result["quotes"]))
        self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_contemporaneous_bookmaker_quotes_still_flag_outlier(self):
        d=event()
        d[0]["commence_time"]="2026-10-09T18:00:00Z"
        for key,price in (("book_b",1.79),("book_c",20.0)):
            book=copy.deepcopy(d[0]["bookmakers"][0])
            book["key"]=key
            book["markets"][0]["outcomes"][0]["price"]=price
            d[0]["bookmakers"].append(book)
        d[0]["bookmakers"][2]["markets"][0]["last_update"]="2026-10-09T13:59:15Z"
        result=run(d)
        self.assertEqual(result["cross_bookmaker_price_outliers"],1)
        self.assertEqual([q["bookmaker"] for q in result["quotes"]
                          if q["cross_bookmaker_price_outlier"]],["book_c"])

    def test_distant_fourth_bookmaker_does_not_suppress_valid_outlier(self):
        d=event()
        d[0]["commence_time"]="2026-10-09T18:00:00Z"
        for key,price in (("book_b",1.79),("book_c",20.0),
                          ("book_d",1.82)):
            book=copy.deepcopy(d[0]["bookmakers"][0])
            book["key"]=key
            book["markets"][0]["outcomes"][0]["price"]=price
            d[0]["bookmakers"].append(book)
        d[0]["bookmakers"][3]["markets"][0]["last_update"]="2026-10-09T13:58:45Z"
        result=run(d)
        self.assertEqual(result["quotes_accepted"],28)
        self.assertEqual(result["cross_bookmaker_price_outliers"],1)
        self.assertEqual([q["bookmaker"] for q in result["quotes"]
                          if q["cross_bookmaker_price_outlier"]],["book_c"])
        self.assertEqual(result["production_recommendations"],"DISABLED")
        d[0]["bookmakers"].reverse()
        again=run(d)
        self.assertEqual([q["bookmaker"] for q in again["quotes"]
                          if q["cross_bookmaker_price_outlier"]],["book_c"])

    def test_audit_counters_distinguish_eligible_from_observed(self):
        d=event()
        d[0]["commence_time"]="2026-10-09T18:00:00Z"
        for key,price in (("book_b",1.79),("book_c",20.0)):
            book=copy.deepcopy(d[0]["bookmakers"][0])
            book["key"]=key
            book["markets"][0]["outcomes"][0]["price"]=price
            d[0]["bookmakers"].append(book)
        result=run(d)
        self.assertEqual(result["quotes_accepted"],21)
        self.assertEqual(result["unverified_quote_count"],21)
        self.assertEqual(result["eligible_prematch_quote_count"],20)
        self.assertEqual(result["prematch_quotes_excluded_by_outlier_check"],1)
        self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_inplay_quotes_never_count_as_eligible_prematch_evidence(self):
        d=event()
        result=run(d)
        self.assertEqual(result["quotes_accepted"],7)
        self.assertEqual(result["unverified_quote_count"],7)
        self.assertEqual(result["eligible_prematch_quote_count"],0)
        self.assertEqual(result["prematch_quotes_excluded_by_outlier_check"],0)

    def test_two_bookmakers_cannot_establish_price_outlier(self):
        d=event()
        d[0]["commence_time"]="2026-10-09T18:00:00Z"
        book=copy.deepcopy(d[0]["bookmakers"][0])
        book["key"]="book_b"
        book["markets"][0]["outcomes"][0]["price"]=20.0
        d[0]["bookmakers"].append(book)
        result=run(d)
        self.assertEqual(result["cross_bookmaker_price_outliers"],0)
        self.assertTrue(all(q["quote_eligible_as_prematch_evidence"]
                            for q in result["quotes"]))
        self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_duplicate_fixture_snapshots_quarantined_in_either_order(self):
        d=event()
        conflicting=copy.deepcopy(d[0])
        conflicting["bookmakers"][0]["markets"][0]["outcomes"][0]["price"]=2.55
        d.append(conflicting)
        first=run(d)
        d.reverse()
        second=run(d)
        for result in (first,second):
            self.assertEqual(result["quotes_accepted"],0)
            self.assertEqual(result["matched_events"],0)
            self.assertEqual(result["reject_reasons"]["DUPLICATE_EVENT_ID"],2)
            self.assertEqual(result["status"],"HOLD")
            self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_unique_fixture_ids_still_processed(self):
        d=event()
        other=copy.deepcopy(d[0])
        other["id"]="fixture2"
        d.append(other)
        result=run(d)
        self.assertEqual(result["matched_events"],2)
        self.assertEqual(result["quotes_accepted"],14)
        self.assertNotIn("DUPLICATE_EVENT_ID",result["reject_reasons"])

    def test_duplicate_bookmaker_snapshots_quarantined_regardless_of_order(self):
        d=event()
        conflicting=copy.deepcopy(d[0]["bookmakers"][0])
        conflicting["markets"][0]["outcomes"][0]["price"]=1.99
        d[0]["bookmakers"].append(conflicting)
        first=run(d)
        d[0]["bookmakers"].reverse()
        second=run(d)
        for result in (first,second):
            self.assertEqual(result["quotes_accepted"],0)
            self.assertEqual(result["reject_reasons"]["DUPLICATE_BOOKMAKER_CONFLICT"],2)
            self.assertEqual(result["status"],"HOLD")
            self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_unique_bookmakers_remain_independent_research_observations(self):
        d=event()
        other=copy.deepcopy(d[0]["bookmakers"][0])
        other["key"]="another-book"
        d[0]["bookmakers"].append(other)
        result=run(d)
        self.assertEqual(result["quotes_accepted"],14)
        self.assertNotIn("DUPLICATE_BOOKMAKER_CONFLICT",result["reject_reasons"])
        self.assertFalse(result["executable_bookmaker_price_verified"])

    def test_duplicate_market_updates_quarantined_in_any_order(self):
        d=event()
        duplicate=copy.deepcopy(d[0]["bookmakers"][0]["markets"][0])
        duplicate["last_update"]="2026-10-09T13:59:59Z"
        duplicate["outcomes"][0]["price"]=1.95
        d[0]["bookmakers"][0]["markets"].append(duplicate)
        first=run(d)
        d[0]["bookmakers"][0]["markets"].reverse()
        second=run(d)
        for result in (first,second):
            self.assertEqual(result["quotes_accepted"],5)
            self.assertEqual(result["reject_reasons"]["DUPLICATE_MARKET_CONFLICT"],2)
            self.assertTrue(all(q["market"]!="totals" for q in result["quotes"]))
            self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_unique_market_types_still_accepted(self):
        result=run(event())
        self.assertEqual(result["quotes_accepted"],7)
        self.assertNotIn("DUPLICATE_MARKET_CONFLICT",result["reject_reasons"])

    def test_duplicate_quote_rejected(self):
        d=event()
        d[0]["bookmakers"][0]["markets"][0]["outcomes"].append(
            dict(d[0]["bookmakers"][0]["markets"][0]["outcomes"][0]))
        result=run(d)
        self.assertEqual(result["reject_reasons"]["DUPLICATE_OUTCOME_CONFLICT"],2)
        self.assertEqual(result["quotes_accepted"],6)

    def test_conflicting_outcome_prices_quarantined_in_any_order(self):
        d=event()
        duplicate=copy.deepcopy(d[0]["bookmakers"][0]["markets"][0]["outcomes"][0])
        duplicate["price"]=2.75
        d[0]["bookmakers"][0]["markets"][0]["outcomes"].append(duplicate)
        first=run(d)
        d[0]["bookmakers"][0]["markets"][0]["outcomes"].reverse()
        second=run(d)
        for result in (first,second):
            self.assertEqual(result["quotes_accepted"],6)
            self.assertEqual(result["reject_reasons"]["DUPLICATE_OUTCOME_CONFLICT"],2)
            self.assertFalse(any(q["market"]=="totals" and q["outcome"]=="Under"
                                 for q in result["quotes"]))
            self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_unmatched_team_does_not_cross_join(self):
        d=event()
        d[0]["home_team"]="Another"
        self.assertEqual(run(d)["quotes_accepted"],0)
        self.assertEqual(run(d)["status"],"HOLD")

    def test_wrong_sport_key_rejected(self):
        d=event()
        d[0]["sport_key"]="soccer_spain_la_liga"
        self.assertEqual(run(d)["reject_reasons"]["WRONG_SPORT_KEY"],1)

    def test_naive_clock_fails_closed(self):
        with self.assertRaises(ValueError):
            extract(event(),captured_utc="2026-10-09T14:00:00",
                    league="soccer_epl",home="Home",away="Away")

    def test_overlong_input_rejected(self):
        with self.assertRaises(ValueError):
            run(event()*201)

    def test_missing_spread_point_rejected(self):
        d=event()
        del d[0]["bookmakers"][0]["markets"][1]["outcomes"][0]["point"]
        self.assertEqual(run(d)["reject_reasons"]["INVALID_ASIAN_POINT"],1)

if __name__=="__main__":
    unittest.main()
