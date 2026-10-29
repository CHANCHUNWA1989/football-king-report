"""Synthetic tests proving forward-only scoring, deduplication and HOLD safety."""
import copy
import gzip
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import forward_validation
from forward_validation import load_archived, extend, report_metrics, valid_prior_sample
from model_ab import MODEL as B_MODEL, candidate as make_b


class ForwardEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.pred = datetime(2026,10,1,8,tzinfo=timezone.utc)
        self.kickoff = self.pred+timedelta(days=1)
        self.now = self.kickoff+timedelta(hours=4)
        self.pair = {
            "league": "bundesliga", "home": "FC Köln", "away": "Bayern",
            "prediction_utc": self.pred.isoformat(),
            "market_snapshot_utc": (self.pred-timedelta(minutes=9)).isoformat(),
            "kickoff_utc": self.kickoff.isoformat(),
            "model": [.3,.3,.4], "market": [.2,.2,.6],
            "production_recommendations": "DISABLED"
        }
        self.report = {"checked_utc": self.now.isoformat(),
                       "fixtures": {"matches": [{
                           "league": "bundesliga", "home": "FC Koln", "away": "Bayern",
                           "kickoff_utc": self.kickoff.isoformat(),
                           "status": "FINISHED", "score_ft": [0,2]}]}}

    def test_later_finished_score_can_be_used_once(self):
        samples=extend({}, [(("bundesliga", "fckoln", "bayern",self.kickoff.isoformat()), self.pair)],self.report)
        self.assertEqual(samples["n"],1)
        self.assertEqual(samples["newly_settled"],1)
        self.assertEqual(samples["samples"][0]["y"],2)
        again=extend(samples, [(("bundesliga", "fckoln", "bayern",self.kickoff.isoformat()), self.pair)],self.report)
        self.assertEqual(again["n"],1)
        self.assertEqual(again["newly_settled"],0)
        stats=report_metrics(again)
        self.assertEqual(stats["status"],"HOLD")
        self.assertEqual(stats["forward_archive_samples"],1)

    def test_unfinished_match_never_scores(self):
        self.report["fixtures"]["matches"][0]["status"]="SCHEDULED"
        r=extend({},[(("bundesliga","fckoln","bayern",self.kickoff.isoformat()),self.pair)],self.report)
        self.assertEqual(r["n"],0)

    def test_score_before_two_hours_is_excluded(self):
        self.report["checked_utc"]=(self.kickoff+timedelta(minutes=90)).isoformat()
        r=extend({},[(("bundesliga","fckoln","bayern",self.kickoff.isoformat()),self.pair)],self.report)
        self.assertEqual(r["n"],0)

    def test_v41_combined_rows_without_league_can_settle_using_source_index(self):
        # The merged V4.1 report drops league; the same fetch that powers
        # Shadow Mode keeps the league on its internal finished observations.
        report={"checked_utc":self.now.isoformat(),
                "fixtures":{"matches":[{
                    "home":"FC Koln","away":"Bayern","date":self.kickoff.date().isoformat(),
                    "kickoff_utc":None,"status":"FINISHED","score_ft":[0,2]}]}}
        results={"schema":"football-king-single-source-finished-results-1",
                 "captured_utc":self.now.isoformat(),
                 "production_recommendations":"DISABLED",
                 "independently_verified_all_leagues":False,
                 "records":[{
                     "league":"bundesliga","home":"FC Köln","away":"Bayern",
                     "date":self.kickoff.date().isoformat(),"kickoff_utc":None,
                     "status":"FINISHED","score_ft":[0,2]}]}
        records=[(("bundesliga","fckoln","bayern",self.kickoff.isoformat()),self.pair)]
        result=extend({},records,report,results)
        self.assertEqual(result["n"],1)
        self.assertEqual(result["samples"][0]["y"],2)
        self.assertFalse(result["samples"][0]["fixture_result_source_independently_verified"])

    def test_wrong_league_or_date_cannot_create_settlement(self):
        report={"checked_utc":self.now.isoformat(),"fixtures":{"matches":[]}}
        results={"schema":"football-king-single-source-finished-results-1",
                 "captured_utc":self.now.isoformat(),
                 "production_recommendations":"DISABLED",
                 "independently_verified_all_leagues":False,
                 "records":[{
                     "league":"epl","home":"FC Köln","away":"Bayern",
                     "date":self.kickoff.date().isoformat(),
                     "status":"FINISHED","score_ft":[0,2]}]}
        rows=[(("bundesliga","fckoln","bayern",self.kickoff.isoformat()),self.pair)]
        self.assertEqual(extend({},rows,report,results)["n"],0)
        results["records"][0]["league"]="bundesliga"
        results["records"][0]["date"]=(self.kickoff.date()+timedelta(days=2)).isoformat()
        self.assertEqual(extend({},rows,report,results)["n"],0)

    def test_ambiguous_finished_scores_require_manual_review(self):
        report={"checked_utc":self.now.isoformat(),"fixtures":{"matches":[]}}
        one={"league":"bundesliga","home":"FC Köln","away":"Bayern",
             "date":self.kickoff.date().isoformat(),
             "status":"FINISHED","score_ft":[0,2]}
        results={"schema":"football-king-single-source-finished-results-1",
                 "captured_utc":self.now.isoformat(),
                 "production_recommendations":"DISABLED",
                 "independently_verified_all_leagues":False,
                 "records":[one,{**one,"score_ft":[1,1]}]}
        rows=[(("bundesliga","fckoln","bayern",self.kickoff.isoformat()),self.pair)]
        self.assertEqual(extend({},rows,report,results)["n"],0)

    def test_archived_future_leakage_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with gzip.open(root/"a.json.gz","wt",encoding="utf-8") as f:
                json.dump({"production_recommendations":"DISABLED",
                           "comparisons":[{**self.pair,"prediction_utc":(self.kickoff+timedelta(hours=1)).isoformat()}]},f)
            self.assertEqual(load_archived(root),[])

    def test_earliest_model_prediction_selected(self):
        early={**self.pair,"model":[.1,.3,.6]}
        later={**self.pair,"prediction_utc":(self.pred+timedelta(hours=1)).isoformat(),
               "model":[.8,.1,.1]}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for filename,record in [("old.json.gz",early),("new.json.gz",later)]:
                with gzip.open(root/filename,"wt",encoding="utf-8") as f:
                    json.dump({"production_recommendations":"DISABLED","comparisons":[record]},f)
            selected=load_archived(root)
            self.assertEqual(len(selected),1)
            self.assertEqual(selected[0][1]["model"],[.1,.3,.6])


    def test_equal_earliest_timestamp_conflict_excluded_regardless_of_file_order(self):
        original = dict(self.pair)
        conflicting = {**self.pair, "model": [.7, .2, .1]}
        for order in ((original, conflicting), (conflicting, original)):
            with self.subTest(order=order[0]["model"]):
                with tempfile.TemporaryDirectory() as d:
                    root = Path(d)
                    for i, row in enumerate(order):
                        with gzip.open(root / f"{i}.json.gz", "wt", encoding="utf-8") as out:
                            json.dump({"production_recommendations": "DISABLED",
                                       "comparisons": [row]}, out)
                    self.assertEqual(load_archived(root), [])

    def test_archived_b_must_equal_the_fixed_formula_before_settlement(self):
        good={**self.pair,"ab":make_b(self.pair["model"]),"ab_model":B_MODEL}
        bad={**good,"ab":[.99,.005,.005]}
        for archived,expected in ((good,1),(bad,0)):
            with self.subTest(variant=archived["ab"]):
                with tempfile.TemporaryDirectory() as d:
                    with gzip.open(Path(d)/"a.json.gz","wt",encoding="utf-8") as f:
                        json.dump({"production_recommendations":"DISABLED",
                                   "comparisons":[archived]},f)
                    self.assertEqual(len(load_archived(d)),expected)

    def test_immutable_prior_b_tampering_is_not_counted(self):
        key=("bundesliga","fckoln","bayern",self.kickoff.isoformat())
        archived={**self.pair,"ab":make_b(self.pair["model"]),"ab_model":B_MODEL}
        original=extend({},[(key,archived)],self.report)
        self.assertEqual(original["n"],1)
        self.assertIn("ab",original["samples"][0])
        altered=dict(original["samples"][0],ab=[.99,.005,.005])
        check=extend({"samples":[altered]},[],self.report)
        self.assertEqual(check["n"],0)
        self.assertEqual(report_metrics(check)["forward_archive_samples"],0)

    def test_identical_archived_replays_count_once(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name in ("first.json.gz", "repeat.json.gz"):
                with gzip.open(root / name, "wt", encoding="utf-8") as out:
                    json.dump({"production_recommendations": "DISABLED",
                               "comparisons": [self.pair]}, out)
            self.assertEqual(len(load_archived(root)), 1)

    def test_later_conflict_does_not_displace_true_earliest_forecast(self):
        early = {**self.pair, "prediction_utc": self.pred.isoformat()}
        late_time = (self.pred + timedelta(hours=1)).isoformat()
        late_a = {**self.pair, "prediction_utc": late_time, "model": [.6, .2, .2]}
        late_b = {**self.pair, "prediction_utc": late_time, "model": [.1, .2, .7]}
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            # Deliberately discover the conflicting later records first.
            for i, row in enumerate((late_a, late_b, early)):
                with gzip.open(root / f"{i}.json.gz", "wt", encoding="utf-8") as out:
                    json.dump({"production_recommendations": "DISABLED",
                               "comparisons": [row]}, out)
            rows = load_archived(root)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][1]["model"], [.3, .3, .4])

    def test_conflicting_earliest_market_baseline_is_quarantined(self):
        different = {**self.pair, "market": [.4, .3, .3]}
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for i, row in enumerate((self.pair, different)):
                with gzip.open(root / f"{i}.json.gz", "wt", encoding="utf-8") as out:
                    json.dump({"production_recommendations": "DISABLED",
                               "comparisons": [row]}, out)
            self.assertEqual(load_archived(root), [])

    def test_future_or_stale_market_update_cannot_enter_archive(self):
        for updated in ((self.pred + timedelta(minutes=1)).isoformat(),
                        (self.pred - timedelta(hours=12)).isoformat(),
                        "not-a-timestamp"):
            with self.subTest(updated=updated):
                candidate = {**self.pair, "market_updated_utc": updated}
                with tempfile.TemporaryDirectory() as d:
                    with gzip.open(Path(d) / "record.json.gz", "wt", encoding="utf-8") as out:
                        json.dump({"production_recommendations": "DISABLED",
                                   "comparisons": [candidate]}, out)
                    self.assertEqual(load_archived(d), [])

    def test_non_string_or_same_team_fixture_never_archived(self):
        for home in (None, [], "Bayern"):
            with self.subTest(home=repr(home)):
                record = {**self.pair, "home": home}
                with tempfile.TemporaryDirectory() as d:
                    with gzip.open(Path(d) / "record.json.gz", "wt", encoding="utf-8") as out:
                        json.dump({"production_recommendations": "DISABLED",
                                   "comparisons": [record]}, out)
                    self.assertEqual(load_archived(d), [])

    def test_previous_settlement_league_cannot_disagree_with_sealed_key(self):
        key=("bundesliga", "fckoln", "bayern", self.kickoff.isoformat())
        good = extend({}, [(key, self.pair)], self.report)
        forged = dict(good["samples"][0], league="epl")
        self.assertEqual(extend({"samples": [forged]}, [], self.report)["n"], 0)

    def test_old_market_baseline_cannot_enter_immutable_archive(self):
        old={**self.pair,
             "market_snapshot_utc":(self.pred-timedelta(hours=14)).isoformat()}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with gzip.open(root/"old-market.json.gz","wt",encoding="utf-8") as f:
                json.dump({"production_recommendations":"DISABLED",
                           "comparisons":[old]},f)
            self.assertEqual(load_archived(root),[])

    def test_malformed_previous_settlements_not_trusted(self):
        prior={"samples":[{"key":"fake","y":True,"production_recommendations":"DISABLED"},
                          {"key":"fake2","y":1,"production_recommendations":"ENABLED"}]}
        self.assertEqual(extend(prior,[],self.report)["n"],0)

    def test_metrics_reason_exists_beyond_300_samples(self):
        evidence={"newly_settled":0,"samples":[{
            "kickoff_utc":(self.kickoff+timedelta(days=i//4)).isoformat(),
            "p":[.2,.3,.5],"m":[.25,.25,.5],"y":i%3
        } for i in range(300)]}
        result=report_metrics(evidence)
        self.assertEqual(result["forward_archive_samples"],300)
        self.assertTrue(result["reason"])
        self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_gzip_bomb_is_bounded_by_decompressed_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            payload={"production_recommendations":"DISABLED","comparisons":[],
                     "padding":"x"*8_100_000}
            with gzip.open(root/"large-expansion.json.gz","wt",encoding="utf-8") as stream:
                json.dump(payload,stream)
            with self.assertRaisesRegex(ValueError,"ARCHIVE_GZIP_EXPANSION_LIMIT"):
                load_archived(root)

    def test_archive_comparisons_must_have_bounded_list_shape(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with gzip.open(root/"not-a-list.json.gz","wt",encoding="utf-8") as stream:
                json.dump({"production_recommendations":"DISABLED",
                           "comparisons":{"bad":"shape"}},stream)
            with self.assertRaisesRegex(ValueError,"ARCHIVE_COMPARISON_COUNT_LIMIT"):
                load_archived(root)

    def test_valid_previous_evidence_survives_next_run(self):
        key=("bundesliga","fckoln","bayern",self.kickoff.isoformat())
        settled=extend({},[(key,self.pair)],self.report)
        after=extend(settled,[],self.report)
        self.assertEqual(after["n"],1)
        self.assertEqual(after["newly_settled"],0)

    def test_tampered_prior_probabilities_do_not_enter_forward_metrics(self):
        key=("bundesliga","fckoln","bayern",self.kickoff.isoformat())
        settled=extend({},[(key,self.pair)],self.report)
        invalid=dict(settled["samples"][0])
        invalid["p"]=[.9,.9,.9]
        self.assertEqual(extend({"samples":[invalid]},[],self.report)["n"],0)

    def test_conflicting_prior_settlements_are_refused(self):
        key=("bundesliga","fckoln","bayern",self.kickoff.isoformat())
        settled=extend({},[(key,self.pair)],self.report)
        fake=dict(settled["samples"][0])
        fake["y"]=0
        with self.assertRaisesRegex(ValueError,"CONFLICTING_PREVIOUS_SETTLEMENT"):
            extend({"samples":[settled["samples"][0],fake]},[],self.report)

    def _identity_pair(self, match_id="83212", days=0):
        shift = timedelta(days=days)
        return dict(self.pair,
                    prediction_utc=(self.pred + shift).isoformat(),
                    market_snapshot_utc=(self.pred + shift - timedelta(minutes=9)).isoformat(),
                    kickoff_utc=(self.kickoff + shift).isoformat(),
                    forecast_event_id="openligadb:" + match_id,
                    source_fixture_identity={"provider": "OpenLigaDB", "match_id": match_id},
                    source_fixture_identity_status="UNAUTHENTICATED",
                    independently_verified=False, eligible_for_model_scoring=False)

    def _identity_key(self, pair):
        return ("bundesliga", "fckoln", "bayern", pair["kickoff_utc"])

    def _prior_with_identity(self):
        pair = self._identity_pair()
        prior = extend({}, [(self._identity_key(pair), self.pair)], self.report)
        for field in ("forecast_event_id", "source_fixture_identity",
                      "source_fixture_identity_status", "independently_verified",
                      "eligible_for_model_scoring"):
            prior["samples"][0][field] = copy.deepcopy(pair[field])
        return prior

    def test_new_settlement_preserves_detached_original_identity_and_research_flags(self):
        pair = self._identity_pair()
        original = copy.deepcopy(pair)
        result = extend({}, [(self._identity_key(pair), pair)], self.report)
        sample = result["samples"][0]
        for field in ("forecast_event_id", "source_fixture_identity",
                      "source_fixture_identity_status"):
            self.assertEqual(sample.get(field), original[field])
        for field in ("independently_verified", "eligible_for_model_scoring",
                      "fixture_result_source_independently_verified"):
            self.assertIs(sample.get(field), False)
        self.assertIs(result["results_independently_verified"], False)
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertEqual((sample["p"], sample["m"], sample["y"]),
                         (original["model"], original["market"], 2))
        sample["source_fixture_identity"]["match_id"] = "changed"
        sample["p"][0] = .9
        self.assertEqual(pair, original)

    def test_identity_survives_next_run_and_generator_is_consumed_once(self):
        pair = self._identity_pair()
        records = ((self._identity_key(pair), pair) for _ in range(1))
        first = extend({}, records, self.report)
        self.assertEqual(first["n"], 1)
        self.assertEqual(first["samples"][0].get("forecast_event_id"), "openligadb:83212")
        second = extend(first, [], self.report)
        self.assertEqual(second["samples"], first["samples"])
        self.assertEqual(second["newly_settled"], 0)

    def test_direct_records_reject_corrupt_or_promoted_optional_identity(self):
        valid = self._identity_pair()
        changes = (
            {"source_fixture_identity": {"provider": "OpenLigaDB", "match_id": "83213"}},
            {"source_fixture_identity_status": "VERIFIED"},
            {"independently_verified": True},
            {"eligible_for_model_scoring": True},
            {"forecast_event_id": None},
        )
        for change in changes:
            with self.subTest(change=change):
                bad = dict(valid, **change)
                result = extend({}, [(self._identity_key(bad), bad)], self.report)
                self.assertEqual(result["n"], 0)

    def test_prior_sample_rejects_corrupt_optional_identity(self):
        original = self._prior_with_identity()["samples"][0]
        self.assertTrue(valid_prior_sample(original))
        for change in (
            {"source_fixture_identity": {"provider": "OpenLigaDB", "match_id": "83213"}},
            {"source_fixture_identity_status": "VERIFIED"},
            {"independently_verified": True},
            {"eligible_for_model_scoring": True},
        ):
            with self.subTest(change=change):
                bad = dict(original, **change)
                self.assertFalse(valid_prior_sample(bad))
                self.assertEqual(extend({"samples": [bad]}, [], self.report)["n"], 0)

    def test_legacy_samples_remain_unchanged_without_identity_backfill(self):
        pair = self._identity_pair()
        legacy = extend({}, [(self._identity_key(pair), self.pair)], self.report)
        before = copy.deepcopy(legacy["samples"])
        result = extend(legacy, [(self._identity_key(pair), pair)], self.report)
        self.assertEqual(result["samples"], before)
        for field in ("forecast_event_id", "source_fixture_identity",
                      "source_fixture_identity_status", "independently_verified",
                      "eligible_for_model_scoring"):
            self.assertNotIn(field, result["samples"][0])

    def test_previous_and_pending_candidate_id_reuse_fails_before_settlement(self):
        previous = self._prior_with_identity()
        before = copy.deepcopy(previous)
        same = self._identity_pair()
        conflict = self._identity_pair(days=1)
        for ordered in ((same, conflict), (conflict, same)):
            with self.subTest(first_kickoff=ordered[0]["kickoff_utc"]):
                with self.assertRaisesRegex(ValueError, "CONFLICTING_SOURCE_FIXTURE_BINDING"):
                    extend(previous, ((self._identity_key(row), row) for row in ordered), self.report)
        self.assertEqual(previous, before)

    def test_candidate_id_reuse_fails_in_either_order_without_results(self):
        first, second = self._identity_pair(), self._identity_pair(days=1)
        report = dict(self.report, fixtures={"matches": []})
        for ordered in ((first, second), (second, first)):
            with self.subTest(first_kickoff=ordered[0]["kickoff_utc"]):
                with self.assertRaisesRegex(ValueError, "CONFLICTING_SOURCE_FIXTURE_BINDING"):
                    extend({}, [(self._identity_key(row), row) for row in ordered], report)

    def test_valid_previous_identity_reuse_fails_in_either_order(self):
        first = self._prior_with_identity()["samples"][0]
        second = dict(first,
                      key=json.dumps(self._identity_key(self._identity_pair(days=1))),
                      kickoff_utc=(self.kickoff + timedelta(days=1)).isoformat(),
                      forecast_utc=(self.pred + timedelta(days=1)).isoformat(),
                      market_utc=(self.pred + timedelta(days=1, minutes=-9)).isoformat())
        for ordered in ((first, second), (second, first)):
            with self.subTest(first_key=ordered[0]["key"]):
                with self.assertRaisesRegex(ValueError, "CONFLICTING_SOURCE_FIXTURE_BINDING"):
                    extend({"samples": list(ordered)}, [], self.report)

    def test_equivalent_prior_kickoff_text_is_the_same_source_binding(self):
        previous = self._prior_with_identity()
        row = previous["samples"][0]
        key = json.loads(row["key"])
        key[3] = self.kickoff.isoformat().replace("+00:00", "Z")
        row["key"] = json.dumps(key)
        self.assertTrue(valid_prior_sample(row))
        original = copy.deepcopy(previous)
        pair = self._identity_pair()
        result = extend(previous, [(self._identity_key(pair), pair)], self.report)
        self.assertEqual(result["n"], 1)
        self.assertEqual(result["newly_settled"], 0)
        self.assertEqual(result["samples"], original["samples"])
        self.assertEqual(previous, original)

    def test_offset_prior_identity_replay_with_matched_result_does_not_duplicate(self):
        previous = self._prior_with_identity()
        row = previous["samples"][0]
        offset = timezone(timedelta(hours=8))
        for field in ("kickoff_utc", "forecast_utc", "market_utc"):
            row[field] = datetime.fromisoformat(row[field]).astimezone(offset).isoformat()
        key = json.loads(row["key"])
        key[3] = row["kickoff_utc"]
        row["key"] = json.dumps(key)
        original = copy.deepcopy(previous)
        self.assertTrue(valid_prior_sample(row))
        pair = self._identity_pair()
        result = extend(previous, [(self._identity_key(pair), pair)], self.report)
        self.assertEqual((result["n"], result["newly_settled"]), (1, 0))
        self.assertEqual(result["samples"], original["samples"])
        self.assertEqual(previous, original)

    def test_canonical_equivalent_prior_rows_deduplicate_without_rewriting_them(self):
        first = self._prior_with_identity()["samples"][0]
        second = copy.deepcopy(first)
        offset = timezone(timedelta(hours=8))
        for field in ("kickoff_utc", "forecast_utc", "market_utc"):
            second[field] = datetime.fromisoformat(second[field]).astimezone(offset).isoformat()
        key = json.loads(second["key"])
        key[3] = second["kickoff_utc"]
        second["key"] = json.dumps(key)
        for ordered in ((first, second), (second, first)):
            with self.subTest(first_key=ordered[0]["key"]):
                previous = {"samples": list(ordered)}
                original = copy.deepcopy(previous)
                result = extend(previous, [], self.report)
                self.assertEqual((result["n"], result["newly_settled"]), (1, 0))
                self.assertEqual(result["samples"], [original["samples"][0]])
                self.assertEqual(previous, original)

    def test_conflicting_canonical_prior_rows_are_refused_in_either_order(self):
        first = self._prior_with_identity()["samples"][0]
        second = dict(first, y=0)
        key = json.loads(second["key"])
        key[3] = self.kickoff.isoformat().replace("+00:00", "Z")
        second["key"] = json.dumps(key)
        for ordered in ((first, second), (second, first)):
            with self.subTest(first_key=ordered[0]["key"]):
                previous = {"samples": list(ordered)}
                original = copy.deepcopy(previous)
                with self.assertRaisesRegex(ValueError, "CONFLICTING_PREVIOUS_SETTLEMENT"):
                    extend(previous, [], self.report)
                self.assertEqual(previous, original)

    def test_deep_unused_candidate_metadata_does_not_affect_settlement(self):
        nested = current = {}
        for _ in range(sys.getrecursionlimit() + 100):
            child = {}
            current["unused"] = child
            current = child
        cyclic = {}
        cyclic["unused"] = cyclic
        for label, metadata in (("deep", nested), ("cyclic", cyclic)):
            with self.subTest(unused_metadata=label):
                pair = self._identity_pair()
                pair["unused_metadata"] = metadata
                result = extend({}, [(self._identity_key(pair), pair)], self.report)
                self.assertEqual(result["n"], 1)
                self.assertNotIn("unused_metadata", result["samples"][0])
                self.assertIs(pair["unused_metadata"], metadata)

    def test_forged_candidate_key_cannot_poison_a_valid_source_binding(self):
        valid, different = self._identity_pair(), self._identity_pair(days=1)
        forged = (self._identity_key(valid), different)
        good = (self._identity_key(valid), valid)
        for ordered in ((forged, good), (good, forged)):
            with self.subTest(first_record=ordered[0][1]["kickoff_utc"]):
                result = extend({}, ordered, self.report)
                self.assertEqual(result["n"], 1)

    def test_source_binding_limit_counts_previous_and_unsettled_candidates_together(self):
        previous = self._prior_with_identity()
        candidates = [self._identity_pair("83213"), self._identity_pair("83214")]
        with patch.object(forward_validation, "MAX_EVIDENCE", 2):
            with self.assertRaisesRegex(ValueError, "TOO_MANY_SOURCE_FIXTURE_IDENTITIES"):
                extend(previous, [(self._identity_key(row), row) for row in candidates], self.report)

    def test_direct_archive_iteration_is_bounded(self):
        pair = self._identity_pair()
        with patch.object(forward_validation, "MAX_EVIDENCE", 2):
            records = ((self._identity_key(pair), pair) for _ in range(3))
            with self.assertRaisesRegex(ValueError, "TOO_MANY_ARCHIVED_FORECASTS"):
                extend({}, records, self.report)


if __name__=="__main__":
    unittest.main()
