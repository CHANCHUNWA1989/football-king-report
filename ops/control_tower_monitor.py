"""Read-only public evidence snapshot. No trading or release action."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

REPO = "CHANCHUNWA1989/football-king-report"
WATCHED_PRS = (381, 382, 384, 397, 398, 399, 400)
MAX_MARKET_AGE = timedelta(hours=10)
MAX_CLOCK_SKEW = timedelta(minutes=5)


def utc_date(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else None


def safe_nonnegative(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def market_health(raw, now):
    """Fail closed: invalid/future/stale research data never becomes current."""
    blocked = {"state": "HOLD", "reason": "INVALID_OR_MISSING_SOURCE",
               "as_of_utc": None, "event_count": None,
               "remaining_credits": None, "age_minutes": None}
    if not isinstance(raw, dict) or raw.get("schema") != "football-king-market-consensus-v1":
        return blocked
    if raw.get("market") != "h2h" or raw.get("status") != "RESEARCH_ONLY":
        return {**blocked, "reason": "MARKET_NOT_RESEARCH_H2H"}
    ts = utc_date(raw.get("as_of_utc"))
    if ts is None:
        return {**blocked, "reason": "INVALID_SOURCE_CLOCK"}
    age = now - ts
    if age < -MAX_CLOCK_SKEW:
        return {**blocked, "reason": "FUTURE_SOURCE_CLOCK"}
    if age > MAX_MARKET_AGE:
        return {**blocked, "reason": "STALE_SOURCE",
                "as_of_utc": ts.isoformat(),
                "age_minutes": int(age.total_seconds() // 60)}
    events = safe_nonnegative(raw.get("event_count"))
    quota = raw.get("quota")
    remaining = safe_nonnegative(quota.get("remaining")) if isinstance(quota, dict) else None
    if events is None or remaining is None:
        return {**blocked, "reason": "INVALID_MARKET_COUNTS"}
    return {"state": "CURRENT_RESEARCH_ONLY",
            "reason": "H2H_ONLY_NOT_EXECUTABLE",
            "as_of_utc": ts.isoformat(), "event_count": events,
            "remaining_credits": remaining,
            "age_minutes": max(0, int(age.total_seconds() // 60))}


def github_api(path, token=None):
    """Only fixed public endpoints; never follow user-supplied URL."""
    allowed = {"branches/main", "pulls?state=open&per_page=100",
               "actions/runs?per_page=100"}
    if path not in allowed:
        raise ValueError("Disallowed endpoint")
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "football-king-control-tower-v1"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = Request("https://api.github.com/repos/" + REPO + "/" + path, headers=headers)
    with urlopen(req, timeout=12) as response:
        payload = response.read(2_000_001)
    if len(payload) > 2_000_000:
        raise ValueError("Oversized GitHub response")
    return json.loads(payload)


def github_health(branch, pull_list, runs_list):
    """Observed CI samples are never a complete set of required checks."""
    good_branch = isinstance(branch, dict) and isinstance(branch.get("commit"), dict)
    main_sha = branch["commit"].get("sha") if good_branch else None
    if not isinstance(main_sha, str) or len(main_sha) != 40:
        main_sha = None
    protected = branch.get("protected") if good_branch and isinstance(branch.get("protected"), bool) else None
    pulls = pull_list if isinstance(pull_list, list) else []
    pulls_by_number = {p.get("number"): p for p in pulls
                       if isinstance(p, dict) and p.get("number") in WATCHED_PRS}
    runs = runs_list.get("workflow_runs", []) if isinstance(runs_list, dict) else []
    if not isinstance(runs, list):
        runs = []
    result = []
    for number in WATCHED_PRS:
        p = pulls_by_number.get(number)
        head_obj = p.get("head") if isinstance(p, dict) else None
        head = head_obj.get("sha") if isinstance(head_obj, dict) else None
        head = head if isinstance(head, str) and len(head) == 40 else None
        matching = [r for r in runs if isinstance(r, dict)
                    and r.get("event") == "pull_request"
                    and head and r.get("head_sha") == head]
        if not matching:
            ci = "UNVERIFIED"
        elif any(r.get("conclusion") in {
            "failure", "cancelled", "timed_out", "startup_failure", "action_required"
        } for r in matching):
            ci = "OBSERVED_FAILURE"
        elif any(r.get("status") != "completed" for r in matching):
            ci = "IN_PROGRESS"
        elif all(r.get("conclusion") == "success" for r in matching):
            ci = "OBSERVED_PASS_NOT_EXHAUSTIVE"
        else:
            ci = "UNVERIFIED"
        result.append({"number": number, "state": "OPEN" if p is not None else "UNKNOWN",
                       "draft": p.get("draft") if isinstance(p, dict) and isinstance(p.get("draft"), bool) else None,
                       "head_sha": head, "ci_sample": ci,
                       "sample_run_count": len(matching)})
    return {"main_sha": main_sha, "main_protected": protected,
            "watched_prs": result,
            "ci_sample_note": "Recent runs only; not complete HEAD checks or release approval."}


def build_snapshot(market, branch=None, prs=None, runs=None, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    m = market_health(market, now)
    gh = github_health(branch, prs, runs)
    issues = []
    if m["state"] != "CURRENT_RESEARCH_ONLY":
        issues.append("MARKET_" + m["reason"])
    if gh["main_sha"] is None:
        issues.append("GITHUB_MAIN_UNVERIFIED")
    if gh["main_protected"] is False:
        issues.append("MAIN_BRANCH_UNPROTECTED")
    elif gh["main_protected"] is not True:
        issues.append("MAIN_BRANCH_PROTECTION_UNVERIFIED")
    if any(p["state"] == "UNKNOWN" for p in gh["watched_prs"]):
        issues.append("PR_STATUS_INCOMPLETE")
    if any(p["ci_sample"] == "OBSERVED_FAILURE" for p in gh["watched_prs"]):
        issues.append("PR_CI_OBSERVED_FAILURE")
    if any(p["ci_sample"] in {"UNVERIFIED", "IN_PROGRESS"} for p in gh["watched_prs"]):
        issues.append("PR_CI_EVIDENCE_INCOMPLETE")
    return {"schema": "football-king-control-tower-v1",
            "generated_at_utc": now.isoformat(),
            "data_scope": "PUBLIC_FOOTBALL_REPOSITORY_ONLY",
            "collector": "READ_ONLY_NO_PROVIDER_CALLS", "market": m,
            "github": gh,
            "monitor_state": "RESEARCH_OBSERVATION" if not issues else "HOLD_INCOMPLETE_EVIDENCE",
            "warnings": issues,
            "production_gate": {"status": "HOLD",
                                "production_recommendations": "DISABLED",
                                "verified_positive_ev": False,
                                "live_execution_allowed": False},
            "evidence_limit": "Refresh clock is not source clock; CI success is not accuracy or approval."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", default="market/latest.json")
    parser.add_argument("--output", default="control-tower-snapshot.json")
    parser.add_argument("--offline", action="store_true",
                        help="No GitHub API calls; force unverified PR/CI")
    args = parser.parse_args()
    try:
        market = json.loads(Path(args.market).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        market = None
    branch = prs = runs = None
    if not args.offline:
        for path, target in (("branches/main", "branch"),
                             ("pulls?state=open&per_page=100", "prs"),
                             ("actions/runs?per_page=100", "runs")):
            try:
                value = github_api(path, os.environ.get("GITHUB_TOKEN"))
            except (OSError, ValueError):
                value = None
            if target == "branch":
                branch = value
            elif target == "prs":
                prs = value
            else:
                runs = value
    snapshot = build_snapshot(market, branch, prs, runs)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print("control_tower_state=" + snapshot["monitor_state"])
    print("market_state=" + snapshot["market"]["state"])
    print("production_gate=HOLD")


if __name__ == "__main__":
    main()
