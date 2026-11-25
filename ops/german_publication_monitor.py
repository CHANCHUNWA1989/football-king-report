"""Read-only German publication correlation and cadence monitor, never dispatch writers."""
import argparse
import gzip
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
import re
from urllib.request import Request, build_opener, HTTPRedirectHandler

from ops.german_schedule_gap import diagnose, stamp
from ops.history_blob_retention_preflight import _git, _unique, _valid_sha, RetentionHold

REPO = "CHANCHUNWA1989/football-king-report"
ROOT = "https://api.github.com/repos/" + REPO
WORKFLOW = ".github/workflows/football-king-german-live.yml"
POINTER = "sources/live_germany_latest.json"
RUNS = ROOT + "/actions/workflows/football-king-german-live.yml/runs?branch=main&per_page=10"
LIMIT = 1024 * 1024
LEAGUES = {"bundesliga", "bundesliga2", "germany_liga3"}


def json_read(raw):
    return json.loads(raw, object_pairs_hook=_unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))


def inspect(repo, main_sha, run, now, previous_run=None):
    if not _valid_sha(main_sha) or _git(repo, "cat-file", "-t", main_sha, limit=64).strip() != b"commit":
        raise ValueError("INVALID_MAIN_PIN")
    if (run.get("repository", {}).get("full_name") != REPO
            or run.get("head_branch") != "main" or run.get("path") != WORKFLOW
            or type(run.get("id")) is not int or run["id"] <= 0):
        raise ValueError("INVALID_RUN_IDENTITY")
    raw = _git(repo, "show", main_sha + ":" + POINTER, limit=LIMIT)
    doc = json_read(raw)
    result = diagnose(doc, run, now)
    coverage = doc["league_coverage"]
    if (not isinstance(coverage, list) or len(coverage) != 3
            or {x["league"] for x in coverage} != LEAGUES
            or any(x.get("production_recommendations") != "DISABLED" for x in coverage)):
        raise ValueError("UNSAFE_COVERAGE")
    collected, created = stamp(doc["collected_utc"]), stamp(run["created_at"])
    result.update(main_sha=main_sha, snapshot_sha256=hashlib.sha256(raw).hexdigest(),
                  snapshot_utc=collected.isoformat(), matches=len(doc["matches"]),
                  coverage_available=sum(x.get("status") == "AVAILABLE" for x in coverage),
                  publication_correlated=False, scheduled_cadence_restored=False)
    if run.get("status") == "completed" and run.get("conclusion") == "success":
        finished = stamp(run["updated_at"])
        if created <= collected <= finished <= now:
            # Publication uses UTC date/hour at archive time; allow boundary crossing.
            for clock in {collected, finished}:
                name = "sources/live_germany/history/" + clock.strftime("%Y/%m/%d/%H-") + str(run["id"]) + ".json.gz"
                try:
                    packed = _git(repo, "show", main_sha + ":" + name, limit=LIMIT)
                except RetentionHold:
                    continue
                with gzip.GzipFile(fileobj=io.BytesIO(packed)) as stream:
                    content = stream.read(LIMIT + 1)
                if content == raw:
                    result.update(publication_correlated=True, archive_path=name)
                    break
    if result["status"] == "WITHIN_RESEARCH_AGE":
        if not result["publication_correlated"]:
            result["status"] = "HOLD_FRESH_POINTER_NOT_RUN_CORRELATED"
        elif result["coverage_available"] != 3 or doc.get("status") != "RESEARCH_ONLY":
            result["status"] = "HOLD_PARTIAL_PROVIDER_COVERAGE"
        else:
            result["status"] = "HOLD_FRESH_RESEARCH_PUBLICATION_CORRELATED"
    if previous_run is not None:
        if (previous_run.get("repository", {}).get("full_name") != REPO
                or previous_run.get("path") != WORKFLOW or previous_run.get("head_branch") != "main"
                or previous_run.get("event") != "schedule" or run.get("event") != "schedule"):
            raise ValueError("INVALID_PREVIOUS_SCHEDULE")
        gap = (created - stamp(previous_run["created_at"])).total_seconds()
        if gap <= 0:
            raise ValueError("NONINCREASING_RUN_CLOCK")
        result.update(previous_schedule_gap_seconds=round(gap),
                      schedule_gap_exceeds_two_hours=gap > 7200)
    return result


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def get(url):
    if url not in (RUNS, ROOT + "/git/ref/heads/main"):
        raise ValueError("UNAPPROVED_OBSERVATION_URL")
    request = Request(url, headers={"Accept":"application/vnd.github+json",
                                    "User-Agent":"football-king-german-readonly"})
    with build_opener(NoRedirect()).open(request, timeout=20) as response:
        raw = response.read(LIMIT+1)
    if len(raw) > LIMIT:
        raise ValueError("OVERSIZED_OBSERVATION")
    return json_read(raw)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--main-sha", required=True)
    p.add_argument("--run-file", type=Path)
    p.add_argument("--previous-run-file", type=Path)
    p.add_argument("--live", action="store_true")
    a = p.parse_args()
    try:
        if a.live:
            if a.run_file or a.previous_run_file or get(ROOT+"/git/ref/heads/main")["object"]["sha"] != a.main_sha:
                raise ValueError("LIVE_MAIN_PIN_CHANGED")
            rows = get(RUNS)["workflow_runs"]
            if not rows or len(rows) > 10:
                raise ValueError("UNBOUNDED_OR_EMPTY_RUNS")
            run = max(rows, key=lambda r: stamp(r["created_at"]))
            scheduled = sorted((r for r in rows if r.get("event") == "schedule" and r["id"] != run["id"]),
                               key=lambda r: stamp(r["created_at"]), reverse=True)
            previous = scheduled[0] if scheduled and run.get("event") == "schedule" else None
        else:
            run = json_read(a.run_file.read_bytes())
            previous = json_read(a.previous_run_file.read_bytes()) if a.previous_run_file else None
        result = inspect(a.repo, a.main_sha, run, datetime.now(timezone.utc), previous)
        if a.live and get(ROOT+"/git/ref/heads/main")["object"]["sha"] != a.main_sha:
            raise ValueError("LIVE_MAIN_PIN_CHANGED")
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, AttributeError, EOFError):
        print(json.dumps(dict(status="HOLD_GERMAN_MONITOR_UNVERIFIABLE", production_recommendations="DISABLED")))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "HOLD_FRESH_RESEARCH_PUBLICATION_CORRELATED" and not result.get("schedule_gap_exceeds_two_hours") else 1


if __name__ == "__main__":
    raise SystemExit(main())
