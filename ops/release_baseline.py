"""Read-only public S0 release baseline; never a betting or promotion gate.

Capture the exact code-main SHA, open PR heads, and deployed research-site
status from fixed HTTPS public endpoints. No credentials or paid market calls.
A complete snapshot does NOT certify source identity, live bookmaker odds,
independent review, branch rulesets, or production readiness.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler

REPO_API = "https://api.github.com/repos/CHANCHUNWA1989/football-king-report"
SITE = "https://chanchunwa1989.github.io/football-king-report"
# GitHub's full PR objects can exceed 1 MiB with fewer than 100 open PRs.
# Page in fixed bounded slices; never relax the per-response size limit.
PR_PAGE_SIZE = 25
MAX_PR_PAGES = 10
PR_PAGE_PREFIX = REPO_API + "/pulls?state=open&per_page=25&page="
URLS = {
    "branch": REPO_API + "/branches/main",
    "pulls": PR_PAGE_PREFIX + "1",
    "status": SITE + "/status.json",
    "quality": SITE + "/quality.json",
    "gate": SITE + "/production_gate.json",
}
MAX_RESPONSE_BYTES = 1_000_000
RECENCY_HOURS = 10
APPROVED_URLS = frozenset(URLS.values()) | frozenset(
    PR_PAGE_PREFIX + str(page) for page in range(2, MAX_PR_PAGES + 1)
)


def _unique_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("DUPLICATE_JSON_FIELD")
        obj[key] = value
    return obj


def _reject_constant(value):
    raise ValueError("NONFINITE_JSON_NUMBER")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def fetch_public_json(url: str):
    if url not in APPROVED_URLS:
        raise ValueError("URL_NOT_APPROVED")
    request = Request(url, headers={
        "Accept": "application/vnd.github+json" if url.startswith(REPO_API)
        else "application/json",
        "User-Agent": "Football-King-S0-Release-Baseline",
    })
    with build_opener(NoRedirect()).open(request, timeout=8) as response:
        if response.geturl() != url or response.status != 200:
            raise ValueError("UNTRUSTED_HTTP_RESPONSE")
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("OVERSIZE_PUBLIC_RESPONSE")
    return json.loads(raw.decode("utf-8"),
                      object_pairs_hook=_unique_pairs,
                      parse_constant=_reject_constant)


def parse_clock(value):
    if not isinstance(value, str):
        raise ValueError("MISSING_UTC_CLOCK")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
        raise ValueError("CLOCK_NOT_EXPLICIT_UTC")
    return dt.astimezone(timezone.utc)


def _is_disabled(obj):
    return isinstance(obj, dict) and obj.get("production_recommendations") == "DISABLED"


def build_baseline(fetch_json=fetch_public_json, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_AUDIT_CLOCK")
    now = now.astimezone(timezone.utc)

    data = {key: fetch_json(url) for key, url in URLS.items()}
    branch, first_pr_page = data["branch"], data["pulls"]
    status, quality, gate = data["status"], data["quality"], data["gate"]
    if not all(isinstance(d, dict) for d in (branch, status, quality, gate)):
        raise ValueError("MALFORMED_PUBLIC_DOCUMENT")
    if not isinstance(first_pr_page, list) or len(first_pr_page) > PR_PAGE_SIZE:
        raise ValueError("OPEN_PR_PAGE_INCOMPLETE")
    pulls = list(first_pr_page)
    page = first_pr_page
    pages_read = 1
    # A full page does not establish that it is the last page. Continue
    # until a shorter page is seen, or fail closed at the hard page cap.
    while len(page) == PR_PAGE_SIZE:
        if pages_read >= MAX_PR_PAGES:
            raise ValueError("OPEN_PR_PAGE_INCOMPLETE")
        pages_read += 1
        page = fetch_json(PR_PAGE_PREFIX + str(pages_read))
        if not isinstance(page, list) or len(page) > PR_PAGE_SIZE:
            raise ValueError("OPEN_PR_PAGE_INCOMPLETE")
        pulls.extend(page)
    sha = branch.get("commit", {}).get("sha")
    if not isinstance(sha, str) or len(sha) != 40 or any(
            char not in "0123456789abcdef" for char in sha):
        raise ValueError("INVALID_MAIN_SHA")
    if type(branch.get("protected")) is not bool:
        raise ValueError("MISSING_BRANCH_PROTECTION_FLAG")
    open_prs = []
    seen = set()
    for pr in pulls:
        if not isinstance(pr, dict):
            raise ValueError("MALFORMED_PULL_REQUEST")
        number = pr.get("number")
        head = pr.get("head", {}).get("sha")
        if (type(number) is not int or number <= 0 or number in seen
                or not isinstance(head, str) or len(head) != 40
                or any(c not in "0123456789abcdef" for c in head)
                or type(pr.get("draft")) is not bool):
            raise ValueError("INVALID_PR_IDENTITY")
        seen.add(number)
        open_prs.append({
            "number": number, "draft": pr["draft"], "head_sha": head,
            "base": pr.get("base", {}).get("ref"),
            "updated_at": pr.get("updated_at"),
        })
    open_prs.sort(key=lambda item: item["number"])

    checked_status = parse_clock(status.get("checked_utc"))
    checked_quality = parse_clock(quality.get("checked_utc"))
    if abs((checked_status-checked_quality).total_seconds()) > 300:
        raise ValueError("INCONSISTENT_PUBLIC_SNAPSHOT_CLOCKS")
    age = (now - checked_status).total_seconds() / 3600
    if age < -(5 / 60):
        raise ValueError("FUTURE_PUBLIC_SNAPSHOT")
    fresh = age <= RECENCY_HOURS
    if (not isinstance(status.get("public_fixture_sources_success"), int)
            or not isinstance(status.get("public_fixture_sources_total"), int)
            or not isinstance(quality.get("public_matches"), int)
            or not isinstance(quality.get("matches_with_precise_kickoff"), int)
            or not isinstance(quality.get("pre_match_snapshot_eligible"), int)):
        raise ValueError("MISSING_SITE_COVERAGE")
    count = quality["public_matches"]
    # The two separately served public documents must describe the same
    # fixture population. A successful HTTP response alone proves neither
    # that the snapshots match nor that they contain all fixtures.
    status_count = status.get("window_matches")
    if type(status_count) is not int or status_count < 0:
        raise ValueError("MISSING_STATUS_MATCH_COUNT")
    if type(count) is not int or count != status_count:
        raise ValueError("INCONSISTENT_PUBLIC_MATCH_COUNTS")
    precise = quality["matches_with_precise_kickoff"]
    eligible = quality["pre_match_snapshot_eligible"]
    if not 0 <= eligible <= precise <= count:
        raise ValueError("INCONSISTENT_SITE_COVERAGE")
    if not 0 <= status["public_fixture_sources_success"] <= status["public_fixture_sources_total"]:
        raise ValueError("INCONSISTENT_SOURCE_HEALTH")

    authenticated = gate.get("authenticated_forward_samples")
    historical = gate.get("recorded_research_samples")
    if (type(authenticated) is not int or authenticated < 0
            or type(historical) is not int or historical < 0):
        raise ValueError("INVALID_SAMPLE_COUNTS")
    disabled_everywhere = all(_is_disabled(obj) for obj in (status, quality, gate))
    safe_to_claim_betting = False
    alert = not disabled_everywhere or gate.get("status") != "HOLD"
    return {
        "schema": "football-king-s0-release-baseline-v1",
        "captured_utc": now.isoformat(),
        "source_urls": dict(URLS),
        "main": {
            "sha": sha, "protected_flag": branch["protected"],
            "branch_protection_independently_enforced": False,
            "writer_reader_migration_verified": False,
        },
        "pull_requests": {
            "count": len(open_prs), "pages_read": pages_read,
            "cross_page_snapshot_atomic": False, "open": open_prs,
        },
        "website": {
            "checked_utc": checked_status.isoformat(),
            "snapshot_age_hours": round(age, 3),
            "fresh_under_ten_hours": fresh,
            "status": status.get("status"),
            "source_success": status["public_fixture_sources_success"],
            "source_total": status["public_fixture_sources_total"],
            "public_matches": count,
            "precise_kickoff": precise,
            "initial_prematch_eligible": eligible,
            "critical_errors": quality.get("critical_errors"),
            "quality_warnings": quality.get("warnings"),
        },
        "qualification": {
            "legacy_research_samples_not_authenticated": historical,
            "website_claimed_authenticated_forward_samples": authenticated,
            "authenticated_samples_independently_checked_here": False,
            "status": gate.get("status"),
            "gate_reason": gate.get("reason"),
            "production_recommendations_disabled_on_all_sources": disabled_everywhere,
        },
        "s0_public_snapshot_captured": True,
        "status": "AUDIT_ALERT" if alert else
                  ("SITE_STALE" if not fresh else "BASELINE_CAPTURED"),
        "independent_reviewer_approved": False,
        "ready_for_release_b": False,
        "verified_positive_ev": False,
        "production_recommendations": "DISABLED",
        "permission_to_trade": safe_to_claim_betting,
        "note": "Public snapshot only; provenance, full writer inventory, rulesets, forward certification and deployment approval not proven.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None,
                        help="Optional local report output; refuses overwrites")
    args = parser.parse_args(argv)
    try:
        report = build_baseline()
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({
            "schema": "football-king-s0-release-baseline-v1",
            "status": "AUDIT_INCOMPLETE",
            "error_type": type(exc).__name__,
            "ready_for_release_b": False,
            "production_recommendations": "DISABLED",
        }, sort_keys=True))
        return 2
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as file:
            file.write(payload)
    print(payload, end="")
    return 0 if report["status"] == "BASELINE_CAPTURED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
