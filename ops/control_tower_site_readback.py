"""S2 read-only deployed-site readback. Never publish, merge or enable betting.

A site response is NOT proof of the exact deployed code commit unless
explicit version fields and matching GitHub Pages deployment-job evidence exist.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

REPO = "CHANCHUNWA1989/football-king-report"
API_ROOT = "https://api.github.com/repos/" + REPO
SITE_ROOT = "https://chanchunwa1989.github.io/football-king-report"
URLS = {
    "branch": API_ROOT + "/branches/main",
    "status": SITE_ROOT + "/status.json",
    "quality": SITE_ROOT + "/quality.json",
    "gate": SITE_ROOT + "/production_gate.json",
}
SHA40 = re.compile(r"^[0-9a-f]{40}$")
MAX_BYTES = 1_000_000
MAX_AGE = timedelta(hours=10)
CLOCK_DRIFT = timedelta(minutes=5)
DEPLOY_WORKFLOW = "Football King V4.1 iPhone Daily Report"
DEPLOY_JOB = "publish"
DEPLOY_STEP = "Deploy mobile site"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def strict_object(pairs):
    value = {}
    for key, entry in pairs:
        if key in value:
            raise ValueError("DUPLICATE_JSON_KEY")
        value[key] = entry
    return value


def reject_constant(value):
    raise ValueError("NONFINITE_JSON_NUMBER")


def sha(value):
    return isinstance(value, str) and SHA40.fullmatch(value) is not None


def utc_clock(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        return None
    if result.tzinfo is None or result.utcoffset() != timedelta(0):
        return None
    return result.astimezone(timezone.utc)


def get_json(url, *, token=None, expected_sha=None, run_id=None):
    """Fixed origin/path; block redirects and unbounded responses."""
    allowed = set(URLS.values())
    if sha(expected_sha):
        allowed.add(API_ROOT + "/actions/runs?head_sha=" + expected_sha + "&per_page=100")
    if isinstance(run_id, int) and not isinstance(run_id, bool) and 0 < run_id < 10**16:
        allowed.add(API_ROOT + "/actions/runs/" + str(run_id) + "/jobs?per_page=100")
    if url not in allowed:
        raise ValueError("UNAPPROVED_READBACK_URL")
    headers = {"Accept": "application/json",
               "User-Agent": "football-king-s2-site-readback"}
    if token and url.startswith(API_ROOT):
        headers["Authorization"] = "Bearer " + token
    try:
        with build_opener(NoRedirect()).open(Request(url, headers=headers), timeout=10) as resp:
            if resp.status != 200 or resp.geturl() != url:
                return None
            payload = resp.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES:
            return None
        return json.loads(payload.decode("utf-8"),
                          object_pairs_hook=strict_object,
                          parse_constant=reject_constant)
    except (HTTPError, URLError, OSError, UnicodeError, ValueError):
        return None


def select_deploy(runs, expected_sha):
    """A successful run is still NOT proof that the public URL serves its bytes."""
    if not isinstance(runs, dict):
        return None, "DEPLOY_RUNS_MISSING"
    items = runs.get("workflow_runs")
    if not isinstance(items, list) or len(items) >= 100:
        return None, "DEPLOY_RUNS_INCOMPLETE"
    candidates = [
        x for x in items if isinstance(x, dict)
        and x.get("name") == DEPLOY_WORKFLOW
        and x.get("head_sha") == expected_sha
        and x.get("head_branch") == "main"
        and x.get("status") == "completed"
        and x.get("conclusion") == "success"
        and x.get("event") in {"push", "schedule", "workflow_run", "workflow_dispatch"}
        and type(x.get("id")) is int and x["id"] > 0
    ]
    if not candidates:
        return None, "EXACT_SHA_DEPLOY_RUN_UNVERIFIED"
    candidates.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
    return candidates[0], None


def evaluate_readback(inputs, expected_sha, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_AUDIT_CLOCK")
    now = now.astimezone(timezone.utc)
    data = inputs if isinstance(inputs, dict) else {}
    issues = []
    branch = data.get("branch")
    branch = branch if isinstance(branch, dict) else {}
    current = branch.get("commit")
    current = current.get("sha") if isinstance(current, dict) else None
    if not sha(expected_sha):
        issues.append("EXPECTED_RELEASE_SHA_INVALID")
    if not sha(current) or current != expected_sha:
        issues.append("MAIN_RELEASE_SHA_NOT_CURRENT")
    if branch.get("protected") is not True:
        issues.append("MAIN_PROTECTION_NOT_VERIFIED")

    status = data.get("status")
    quality = data.get("quality")
    gate = data.get("gate")
    if not all(isinstance(item, dict) for item in (status, quality, gate)):
        issues.append("PUBLIC_SITE_DOCUMENTS_MISSING")
        status = status if isinstance(status, dict) else {}
        quality = quality if isinstance(quality, dict) else {}
        gate = gate if isinstance(gate, dict) else {}

    s_time = utc_clock(status.get("checked_utc"))
    q_time = utc_clock(quality.get("checked_utc"))
    age_seconds = None
    if s_time is None or q_time is None:
        issues.append("SITE_CAPTURE_CLOCK_INVALID")
    else:
        if abs((s_time - q_time).total_seconds()) > CLOCK_DRIFT.total_seconds():
            issues.append("SITE_STATUS_QUALITY_CLOCK_MISMATCH")
        age_seconds = (now - s_time).total_seconds()
        if not (-CLOCK_DRIFT.total_seconds() <= age_seconds <= MAX_AGE.total_seconds()):
            issues.append("SITE_CAPTURE_STALE_OR_FUTURE")

    # These three documents must not claim any executable wagering permission.
    if any(item.get("production_recommendations") != "DISABLED"
           for item in (status, quality, gate)):
        issues.append("PUBLIC_RECOMMENDATIONS_NOT_DISABLED")
    if gate.get("status") != "HOLD":
        issues.append("PUBLIC_PRODUCTION_GATE_NOT_HOLD")
    if gate.get("automated_release_supported") is not False:
        issues.append("PUBLIC_AUTOMATED_RELEASE_NOT_DISABLED")
    if gate.get("model_promoted") is not False:
        issues.append("PUBLIC_MODEL_PROMOTION_NOT_DISABLED")
    if status.get("status") not in ("HOLD", "RESEARCH_ONLY"):
        issues.append("PUBLIC_RESEARCH_STATE_INVALID")
    elif status.get("status") == "HOLD":
        issues.append("PUBLIC_RESEARCH_SOURCE_HOLD")
    if status.get("quality_status") != quality.get("status"):
        issues.append("PUBLIC_QUALITY_STATE_MISMATCH")
    if quality.get("critical_errors"):
        issues.append("PUBLIC_CRITICAL_QUALITY_ERRORS")
    a, b = status.get("window_matches"), quality.get("public_matches")
    if type(a) is not int or type(b) is not int or a < 0 or b < 0 or a != b:
        issues.append("PUBLIC_MATCH_COUNTS_INCONSISTENT")
    precise = quality.get("matches_with_precise_kickoff")
    eligible = quality.get("pre_match_snapshot_eligible")
    if not all(type(x) is int for x in (b, precise, eligible)) or not (0 <= eligible <= precise <= b):
        issues.append("PUBLIC_ELIGIBILITY_COUNTS_INVALID")

    run, err = select_deploy(data.get("runs"), expected_sha)
    if err:
        issues.append(err)
    else:
        jobs_data = data.get("jobs")
        jobs = jobs_data.get("jobs") if isinstance(jobs_data, dict) else None
        if not isinstance(jobs, list) or len(jobs) >= 100:
            issues.append("DEPLOY_JOB_RECORD_INCOMPLETE")
        else:
            matched = [j for j in jobs if isinstance(j, dict)
                       and j.get("run_id") == run["id"] and j.get("name") == DEPLOY_JOB
                       and j.get("status") == "completed" and j.get("conclusion") == "success"]
            if len(matched) != 1:
                issues.append("DEPLOY_JOB_NOT_VERIFIED")
            else:
                steps = matched[0].get("steps")
                if not isinstance(steps, list) or not any(
                    isinstance(step, dict) and step.get("name") == DEPLOY_STEP
                    and step.get("status") == "completed" and step.get("conclusion") == "success"
                    for step in steps
                ):
                    issues.append("PAGES_DEPLOY_STEP_NOT_VERIFIED")

    # Current public site may have no deployed commit marker. Never infer it
    # from GitHub main or from the existence of a successful workflow.
    # Even matching untrusted site fields are corroboration, not signed provenance.
    markers = [item.get("source_commit_sha") for item in (status, quality, gate)]
    if not sha(expected_sha) or any(marker != expected_sha for marker in markers):
        issues.append("PUBLIC_SITE_RELEASE_SHA_NOT_ATTESTED")

    # These are strictly separate domains:
    # (1) website safety and freshness, (2) purported deployment lineage,
    # (3) authorized release. A research-only site cannot authorize bets.
    return {
        "schema": "football-king-s2-public-readback-v1",
        "captured_at_utc": now.isoformat(),
        "expected_main_sha": expected_sha if sha(expected_sha) else None,
        "observed_main_sha": current if sha(current) else None,
        "site_checked_utc": s_time.isoformat() if s_time else None,
        "site_age_minutes": max(0, int(age_seconds // 60)) if age_seconds is not None else None,
        "status": "HOLD" if issues else "CONSISTENT_RESEARCH_ONLY_NOT_AUTHORIZED",
        "blockers": sorted(set(issues)),
        "release_authorized": False,
        "pages_deployment_authorized": False,
        "production_recommendations": "DISABLED",
        "live_execution_allowed": False,
        "verified_positive_ev": False,
        "limitations": (
            "Site self-declared SHA and GitHub deploy step do not prove independent provenance; "
            "actual bytes, license, independent review, branch rules and human approval are separate."
        ),
    }


def collect(expected_sha, token=None):
    """No provider access, no writes, fixed site and GitHub endpoints only."""
    bundle = {key: get_json(url, token=token) for key, url in URLS.items()}
    if not sha(expected_sha):
        return bundle
    runs_url = API_ROOT + "/actions/runs?head_sha=" + expected_sha + "&per_page=100"
    runs = get_json(runs_url, token=token, expected_sha=expected_sha)
    bundle["runs"] = runs
    run, _ = select_deploy(runs, expected_sha)
    if run is not None:
        rid = run["id"]
        bundle["jobs"] = get_json(
            API_ROOT + "/actions/runs/" + str(rid) + "/jobs?per_page=100",
            token=token, run_id=rid
        )
    return bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-main-sha", required=True)
    parser.add_argument("--output", default="control-tower-site-readback.json")
    parser.add_argument("--offline", action="store_true",
                        help="No network, fail closed on missing evidence")
    args = parser.parse_args()
    inputs = {} if args.offline else collect(args.expected_main_sha, os.getenv("GITHUB_TOKEN"))
    result = evaluate_readback(inputs, args.expected_main_sha)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("site_readback=" + result["status"])
    print("blockers=" + ",".join(result["blockers"]))
    print("release_authorized=false; pages_deployment_authorized=false")
    print("production_recommendations=DISABLED; live_execution_allowed=false")


if __name__ == "__main__":
    main()
