"""Offline regression: public S0 baseline cannot certify production or EV."""
import copy
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release_baseline import URLS, build_baseline, fetch_public_json, _unique_pairs

NOW = datetime(2026, 11, 3, 4, 20, tzinfo=timezone.utc)
STAMP = (NOW-timedelta(hours=1)).isoformat()


def payload():
    return {
        "branch": {"name": "main", "protected": False,
                   "commit": {"sha": "a" * 40}},
        "pulls": [
            {"number": 381, "draft": True, "head": {"sha": "b" * 40},
             "base": {"ref": "main"}, "updated_at": STAMP},
            {"number": 382, "draft": True, "head": {"sha": "c" * 40},
             "base": {"ref": "main"}, "updated_at": STAMP}],
        "status": {"checked_utc": STAMP, "status": "RESEARCH_ONLY",
                   "public_fixture_sources_success": 6,
                   "public_fixture_sources_total": 6,
                   "window_matches": 165,
                   "production_recommendations": "DISABLED"},
        "quality": {"checked_utc": STAMP, "public_matches": 165,
                    "matches_with_precise_kickoff": 21,
                    "pre_match_snapshot_eligible": 18,
                    "critical_errors": [],
                    "warnings": ["UPSTREAM_PUBLICATION_TIME_NOT_FULLY_KNOWN"],
                    "production_recommendations": "DISABLED"},
        "gate": {"authenticated_forward_samples": 0,
                 "recorded_research_samples": 73,
                 "status": "HOLD",
                 "reason": "at_least_300_settled_point_in_time_samples",
                 "production_recommendations": "DISABLED"},
    }


def evaluate(data, now=NOW):
    inverse = {url: key for key, url in URLS.items()}
    return build_baseline(lambda url: data[inverse[url]], now=now)


class S0ReleaseBaselineTests(unittest.TestCase):
    def test_captures_baseline_but_never_approves_release(self):
        result = evaluate(payload())
        self.assertEqual(result["status"], "BASELINE_CAPTURED")
        self.assertEqual(result["main"]["sha"], "a" * 40)
        self.assertFalse(result["main"]["protected_flag"])
        self.assertEqual([x["number"] for x in result["pull_requests"]["open"]],
                         [381, 382])
        self.assertEqual(result["website"]["public_matches"], 165)
        self.assertEqual(result["website"]["precise_kickoff"], 21)
        self.assertEqual(result["website"]["initial_prematch_eligible"], 18)
        self.assertEqual(result["qualification"]["legacy_research_samples_not_authenticated"], 73)
        self.assertEqual(result["qualification"]["website_claimed_authenticated_forward_samples"], 0)
        self.assertFalse(result["qualification"]["authenticated_samples_independently_checked_here"])
        self.assertFalse(result["main"]["branch_protection_independently_enforced"])
        self.assertFalse(result["ready_for_release_b"])
        self.assertFalse(result["verified_positive_ev"])
        self.assertFalse(result["permission_to_trade"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_stale_site_is_not_accepted_as_fresh(self):
        data = payload()
        old = (NOW-timedelta(hours=15)).isoformat()
        data["status"]["checked_utc"] = old
        data["quality"]["checked_utc"] = old
        result = evaluate(data)
        self.assertEqual(result["status"], "SITE_STALE")
        self.assertFalse(result["website"]["fresh_under_ten_hours"])
        self.assertFalse(result["ready_for_release_b"])

    def test_non_disabled_published_recommendations_raise_release_alert(self):
        data = payload()
        data["quality"]["production_recommendations"] = "ENABLED"
        result = evaluate(data)
        self.assertEqual(result["status"], "AUDIT_ALERT")
        self.assertFalse(result["qualification"]["production_recommendations_disabled_on_all_sources"])
        self.assertFalse(result["permission_to_trade"])

    def test_gate_not_on_hold_raise_release_alert(self):
        data = payload()
        data["gate"]["status"] = "READY"
        result = evaluate(data)
        self.assertEqual(result["status"], "AUDIT_ALERT")
        self.assertFalse(result["ready_for_release_b"])

    def test_future_time_refused(self):
        data = payload()
        future = (NOW+timedelta(hours=3)).isoformat()
        data["status"]["checked_utc"] = future
        data["quality"]["checked_utc"] = future
        with self.assertRaisesRegex(ValueError, "FUTURE_PUBLIC_SNAPSHOT"):
            evaluate(data)

    def test_site_inconsistent_clocks_refused(self):
        data = payload()
        data["quality"]["checked_utc"] = (NOW-timedelta(minutes=1)).isoformat()
        with self.assertRaisesRegex(ValueError, "INCONSISTENT_PUBLIC_SNAPSHOT_CLOCKS"):
            evaluate(data)

    def test_inconsistent_coverage_refused(self):
        data = payload()
        data["quality"]["pre_match_snapshot_eligible"] = 22
        with self.assertRaisesRegex(ValueError, "INCONSISTENT_SITE_COVERAGE"):
            evaluate(data)

    def test_missing_or_malformed_main_and_pr_info_refused(self):
        data = payload()
        data["branch"]["commit"]["sha"] = "badsha"
        with self.assertRaisesRegex(ValueError, "INVALID_MAIN_SHA"):
            evaluate(data)
        data = payload()
        data["pulls"][0]["head"]["sha"] = "bad"
        with self.assertRaisesRegex(ValueError, "INVALID_PR_IDENTITY"):
            evaluate(data)

    def test_full_pr_page_fails_closed(self):
        data = payload()
        data["pulls"] = [copy.deepcopy(data["pulls"][0]) for _ in range(100)]
        with self.assertRaisesRegex(ValueError, "OPEN_PR_PAGE_INCOMPLETE"):
            evaluate(data)

    def test_matching_public_match_counts_remain_research_only(self):
        data = payload()
        data["status"]["window_matches"] = 165
        out = evaluate(data)
        self.assertEqual(out["status"], "BASELINE_CAPTURED")
        self.assertEqual(out["website"]["public_matches"], 165)
        self.assertFalse(out["ready_for_release_b"])
        self.assertEqual(out["production_recommendations"], "DISABLED")

    def test_status_quality_disagree_on_fixture_count_fails_closed(self):
        data = payload()
        data["status"]["window_matches"] = 166
        with self.assertRaisesRegex(
                ValueError, "INCONSISTENT_PUBLIC_MATCH_COUNTS"):
            evaluate(data)

    def test_status_quality_missing_public_count_fails_closed(self):
        data = payload()
        data["status"].pop("window_matches", None)
        with self.assertRaisesRegex(ValueError, "MISSING_STATUS_MATCH_COUNT"):
            evaluate(data)

    def test_missing_provenance_and_bad_sample_counts_refused(self):
        data = payload()
        data["gate"]["authenticated_forward_samples"] = -1
        with self.assertRaisesRegex(ValueError, "INVALID_SAMPLE_COUNTS"):
            evaluate(data)
        data = payload()
        data["quality"]["pre_match_snapshot_eligible"] = "18"
        with self.assertRaisesRegex(ValueError, "MISSING_SITE_COVERAGE"):
            evaluate(data)

    def test_unapproved_url_and_duplicate_json_fields_refused(self):
        with self.assertRaisesRegex(ValueError, "URL_NOT_APPROVED"):
            fetch_public_json("https://evil.invalid/credentials")
        with self.assertRaisesRegex(ValueError, "DUPLICATE_JSON_FIELD"):
            _unique_pairs([("x", 1), ("x", 2)])

    def test_missing_timezone_refused(self):
        data = payload()
        data["status"]["checked_utc"] = "2026-11-03T03:20:00"
        with self.assertRaisesRegex(ValueError, "CLOCK_NOT_EXPLICIT_UTC"):
            evaluate(data)


class S0OpenPrPaginationRegressionTests(unittest.TestCase):
    """S0 must enumerate a growing PR queue without unbounded HTTP replies."""

    def _pr(self, number):
        return {"number": number, "draft": False,
                "head": {"sha": format(number, "040x")},
                "base": {"ref": "main"}, "updated_at": STAMP}

    def _evaluate_pages(self, first, other_pages):
        data = payload()
        data["pulls"] = first
        inverse = {url: key for key, url in URLS.items()}
        requested = []

        def fetch(url):
            requested.append(url)
            if url in inverse:
                return data[inverse[url]]
            for page, rows in other_pages.items():
                if url.endswith("&page=" + str(page)):
                    return rows
            raise AssertionError("UNEXPECTED_UNAPPROVED_PR_PAGE: " + url)

        return build_baseline(fetch, now=NOW), requested

    def test_full_first_page_fetches_next_without_incomplete_snapshot(self):
        first = [self._pr(n) for n in range(400, 425)]
        second = [self._pr(n) for n in range(425, 440)]
        report, urls = self._evaluate_pages(first, {2: second})
        self.assertEqual(report["pull_requests"]["count"], 40)
        self.assertEqual(report["pull_requests"]["pages_read"], 2)
        self.assertEqual(report["status"], "BASELINE_CAPTURED")
        self.assertFalse(report["permission_to_trade"])
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertTrue(any(url.endswith("&page=2") for url in urls))

    def test_overfull_single_page_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "OPEN_PR_PAGE_INCOMPLETE"):
            self._evaluate_pages([self._pr(n) for n in range(400, 426)], {})

    def test_duplicate_identity_across_pages_fails_closed(self):
        first = [self._pr(n) for n in range(400, 425)]
        with self.assertRaisesRegex(ValueError, "INVALID_PR_IDENTITY"):
            self._evaluate_pages(first, {2: [self._pr(424)]})

    def test_page_cap_fails_closed_when_pr_queue_does_not_end(self):
        first = [self._pr(n) for n in range(400, 425)]
        extra = {page: [self._pr(n) for n in
                         range(400 + 25 * (page - 1), 425 + 25 * (page - 1))]
                 for page in range(2, 11)}
        with self.assertRaisesRegex(ValueError, "OPEN_PR_PAGE_INCOMPLETE"):
            self._evaluate_pages(first, extra)


if __name__ == "__main__":
    unittest.main()
