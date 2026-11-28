"""Read-only, bounded historical gap audit. Never writes settlement or certifies results."""
import argparse
import gzip
import hashlib
import io
import json
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

from ops.source_publish_guard import LEAGUES, time, verify
from ops.team_identity import team_id

MAX_FILES = 400
MAX_COMPRESSED = 150000
MAX_DECODED = 500000
MAX_TARGETS = 100
MAX_MATCHES = 2000
WINDOW_DAYS = 3
GAP = "WAITING_FOR_MATCHED_FINISHED_SCORE"


def audit(backlog, root):
    if (not isinstance(backlog, dict)
            or backlog.get("schema") != "football-king-forward-cohort-backlog-v1"
            or backlog.get("production_recommendations") != "DISABLED"
            or backlog.get("pending_fixtures_not_displayed") != 0):
        raise ValueError("UNSAFE_OR_TRUNCATED_BACKLOG")
    now = time(backlog["as_of_utc"])
    rows = backlog["pending_fixtures"]
    if not isinstance(rows, list) or len(rows) > MAX_TARGETS:
        raise ValueError("TARGET_LIMIT")
    targets, days = {}, set()
    for row in rows:
        if (row.get("production_recommendations") != "DISABLED"
                or row.get("independently_verified") is not False):
            raise ValueError("UNSAFE_TARGET")
        if row.get("state") != GAP:
            continue
        league = row["league"]
        home, away = (team_id(league, row[k]) for k in ("home_id", "away_id"))
        ko = time(row["kickoff_utc"])
        if league not in LEAGUES or not home or not away or home == away or now < ko + timedelta(hours=2):
            raise ValueError("INVALID_TARGET")
        key = (league, home, away, ko)
        if key in targets:
            raise ValueError("DUPLICATE_CANONICAL_TARGET")
        targets[key] = {}
        for n in range(WINDOW_DAYS + 1):
            day = ko.date() + timedelta(days=n)
            if day <= now.date():
                days.add(day)
    if len(targets) != backlog.get("unmatched_finished_result_backlog"):
        raise ValueError("TARGET_COUNT_MISMATCH")
    root = Path(root)
    files, missing = [], 0
    for day in sorted(days):
        folder = root / day.strftime("%Y/%m/%d")
        if not folder.is_dir() or any(p.is_symlink() for p in (root, folder.parent.parent, folder.parent, folder)):
            missing += 1
            continue
        for path in folder.iterdir():
            if path.name.endswith(".json.gz"):
                files.append(path)
                if len(files) > MAX_FILES:
                    raise ValueError("TARGETED_FILE_LIMIT")
    by_pair = defaultdict(list)
    for key in targets:
        by_pair[key[:3]].append(key)
    rejected = valid = matched = 0
    for path in sorted(files):
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_COMPRESSED:
                raise ValueError("UNSAFE_ARCHIVE")
            with path.open("rb") as f:
                compressed = f.read(MAX_COMPRESSED + 1)
            if len(compressed) > MAX_COMPRESSED:
                raise ValueError("ARCHIVE_TOO_LARGE")
            with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as f:
                raw = f.read(MAX_DECODED + 1)
            if len(raw) > MAX_DECODED:
                raise ValueError("DECODE_LIMIT")
            doc = json.loads(raw)
            end = verify(doc, now=now)
            start = time(doc["started_utc"])
            if end > now:
                raise ValueError("FUTURE_ARCHIVE")
            digest = hashlib.sha256(compressed).hexdigest()
        except (OSError, EOFError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
            rejected += 1
            continue
        valid += 1
        for row in doc["sampled_fixtures"]:
            if row["status"] != "FINISHED" or row.get("score_ft") is None:
                continue
            league = row["league"]
            pair = (league, team_id(league, row["home"]), team_id(league, row["away"]))
            ko = time(row["kickoff_utc"])
            if start < ko + timedelta(hours=2):
                continue
            for target in by_pair.get(pair, []):
                if abs(ko - target[3]) > timedelta(minutes=45):
                    continue
                if start < target[3] + timedelta(hours=2) or end > target[3] + timedelta(days=WINDOW_DAYS+1):
                    continue
                ident = (row["provider"], row["provider_event_id"], ko.isoformat(), tuple(row["score_ft"]))
                if ident not in targets[target]:
                    matched += 1
                    if matched > MAX_MATCHES:
                        raise ValueError("TARGETED_MATCH_LIMIT")
                    targets[target][ident] = {
                        "provider": ident[0], "provider_event_id": ident[1],
                        "recorded_kickoff_utc": ident[2], "score_ft": list(ident[3]),
                        "archive": path.relative_to(root).as_posix(),
                        "archive_sha256": digest, "collection_started_utc": start.isoformat(),
                        "collection_finished_utc": end.isoformat(),
                    }
    # Conflicting score or multiple native IDs within one provider cannot be
    # resolved by observation order. Cross-provider agreement is not certification.
    native_targets = defaultdict(set)
    for key, obs in targets.items():
        for provider, native, _, _ in obs:
            native_targets[(provider, native)].add(key)
    result = []
    for key, obs in sorted(targets.items()):
        scores = {i[3] for i in obs}
        ids = defaultdict(set)
        for provider, native, _, _ in obs:
            ids[provider].add(native)
        conflict = (len(scores) > 1 or any(len(v)>1 for v in ids.values())
                    or any(len(native_targets[(i[0], i[1])]) > 1 for i in obs))
        status = "CONFLICT" if conflict else "OBSERVED_UNVERIFIED" if obs else "NO_MATCH_IN_SCANNED_WINDOW"
        result.append({"league": key[0], "home_id": key[1], "away_id": key[2],
                       "recorded_kickoff_utc": key[3].isoformat(), "status": status,
                       "observations": [obs[i] for i in sorted(obs)], "independently_verified": False})
    return {"schema": "football-king-targeted-historical-gap-audit-v1", "status": "HOLD",
            "as_of_utc": now.isoformat(), "target_count": len(targets), "files_inspected": len(files),
            "valid_files": valid, "rejected_files": rejected, "missing_day_directories": missing,
            "selected_window_has_read_errors_or_missing_days": bool(missing or rejected),
            "window_days_after_kickoff_date": WINDOW_DAYS, "archive_scope_exhaustive": False,
            "observed_unverified_targets": sum(r["status"] == "OBSERVED_UNVERIFIED" for r in result),
            "conflicting_targets": sum(r["status"] == "CONFLICT" for r in result),
            "no_match_targets": sum(r["status"] == "NO_MATCH_IN_SCANNED_WINDOW" for r in result),
            "targets": result, "authenticated_samples": 0, "formal_metrics": None,
            "executed_api_queries": 0, "production_recommendations": "DISABLED"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backlog", required=True)
    parser.add_argument("--root", default="sources/history")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = audit(json.loads(Path(args.backlog).read_text(encoding="utf-8")), args.root)
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
