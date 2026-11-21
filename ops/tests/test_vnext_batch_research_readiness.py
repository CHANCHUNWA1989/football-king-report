"""No positive betting status may be inferred from public research aggregates."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from ops.vnext_batch_research_readiness import evaluate, _summary_text

NOW = datetime(2026,11,21,9,0,tzinfo=timezone.utc)


def docs():
    collection={
        "schema":"football-king-free-market-collection-status-v1",
        "as_of_utc":"2026-11-21T08:12:35Z",
        "collection_status":"HOLD",
        "collection_reason":"FREE_QUOTA_GUARD",
        "quota":{"used":359,"remaining":141,"last":0},
        "production_recommendations":"DISABLED",
    }
    summary={
        "schema":"football-king-public-artifact-summary-v1",
        "captured_utc":"2026-11-20T17:58:01Z",
        "counts":{"RESEARCH_ONLY":750,"VERIFIED_VALUE":0},
        "evidence_progress":{
            "settled_cases_in_archive":104,
            "independently_verified_result_cases":0,
        },
        "quotes_are_executable":False,
        "raw_prices_or_bookmakers_included":False,
        "production_recommendations":"DISABLED",
    }
    settled={
        "schema":"football-king-settled-archive-v1",
        "checked_utc":"2026-11-21T02:56:04Z",
        "n":105,"results_independently_verified":False,
        "production_recommendations":"DISABLED",
    }
    return collection,summary,settled


class BatchResearchReadinessTests(unittest.TestCase):
    def test_repository_synthetic_zero_certified_not_750_or_105(self):
        report=evaluate(*docs(),now=NOW)
        self.assertEqual(report["status"],"HOLD")
        self.assertEqual(report["public_research_quote_observations"],750)
        self.assertEqual(report["public_settled_research_rows"],105)
        self.assertEqual(report["public_summary_archive_rows_as_of_earlier_snapshot"],104)
        self.assertEqual(report["market_collector_status"],"HOLD")
        self.assertEqual(report["market_collection_reason"],"FREE_QUOTA_GUARD")
        self.assertEqual(report["independently_certified_forward_cases"],0)
        self.assertEqual(report["missing_independently_certified_cases"],300)
        self.assertEqual(report["verified_positive_ev_bets"],0)
        self.assertFalse(report["betting_recommendation_allowed"])
        self.assertFalse(report["model_promotion_allowed"])
        self.assertEqual(report["production_recommendations"],"DISABLED")

    def test_claimed_300_certified_still_counts_as_zero(self):
        collection,summary,settled=docs()
        summary["evidence_progress"]["independently_verified_result_cases"]=300
        summary["counts"]["VERIFIED_VALUE"]=300
        settled["n"]=300
        report=evaluate(collection,summary,settled,now=NOW)
        self.assertEqual(report["public_independence_claims_disregarded"],300)
        self.assertEqual(report["market_value_claims_disregarded"],300)
        self.assertEqual(report["independently_certified_forward_cases"],0)
        self.assertEqual(report["verified_positive_ev_bets"],0)

    def test_public_releases_flags_must_not_be_promoted(self):
        for idx in range(3):
            docs_=list(docs())
            docs_[idx]["production_recommendations"]="ENABLED"
            with self.subTest(idx=idx):
                result=evaluate(*docs_,now=NOW)
                self.assertEqual(result["reason"],"PUBLIC_SOURCE_RELEASE_POLICY_CONFLICT")
                self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_executable_quote_or_independent_ft_claim_rejected(self):
        collection,summary,settled=docs()
        summary["quotes_are_executable"]=True
        self.assertEqual(evaluate(collection,summary,settled,now=NOW)["reason"],
                         "UNSAFE_PUBLIC_SOURCE_CLAIM")
        summary["quotes_are_executable"]=False
        settled["results_independently_verified"]=True
        self.assertEqual(evaluate(collection,summary,settled,now=NOW)["reason"],
                         "UNSAFE_PUBLIC_SOURCE_CLAIM")

    def test_boolean_negative_nan_counts_or_missing_fields_fail_closed(self):
        for value in (True,-1,3.7,None):
            collection,summary,settled=docs()
            summary["counts"]["RESEARCH_ONLY"]=value
            with self.subTest(value=value):
                out=evaluate(collection,summary,settled,now=NOW)
                self.assertEqual(out["reason"],"INVALID_PUBLIC_COUNT_VALUE")
                self.assertEqual(out["independently_certified_forward_cases"],0)
        collection,summary,settled=docs()
        collection["quota"]=None
        self.assertEqual(evaluate(collection,summary,settled,now=NOW)["reason"],
                         "INVALID_PUBLIC_COUNT_SHAPE")

    def test_future_or_stale_evidence_remains_hold(self):
        collection,summary,settled=docs()
        collection["as_of_utc"]="2026-11-22T09:00:00Z"
        out=evaluate(collection,summary,settled,now=NOW)
        self.assertFalse(out["public_snapshots_fresh_24h"]["collection"])
        self.assertEqual(out["reason"],"PUBLIC_SNAPSHOTS_STALE_OR_UNKNOWN")
        self.assertEqual(out["production_recommendations"],"DISABLED")
        out=evaluate(*docs(),now=NOW+timedelta(days=30))
        self.assertEqual(out["independently_certified_forward_cases"],0)

    def test_missing_invalid_timezone_or_wrong_type_clocks(self):
        collection,summary,settled=docs()
        summary["captured_utc"]="2026-11-21T08:00:00"
        out=evaluate(collection,summary,settled,now=NOW)
        self.assertFalse(out["public_snapshots_fresh_24h"]["market_summary"])
        out=evaluate(*docs(),now="2026-11-21T09:00:00Z")
        self.assertEqual(out["reason"],"INVALID_AUDIT_CLOCK")

    def test_markdown_does_not_expose_private_prices_or_promote(self):
        result=evaluate(*docs(),now=NOW)
        body=_summary_text(result)
        self.assertIn("750",body)
        self.assertIn("105",body)
        self.assertIn("0/300",body)
        self.assertIn("DISABLED",body)
        self.assertNotIn("bookmaker",body.lower())
        self.assertNotIn("1.96",body)


if __name__=="__main__":
    unittest.main()
