"""No-network recovery of already archived FREE finished scores.

Reads only sanitized, previously published gzip snapshots under sources/history.
This improves *availability* of older provisional FT observations. It cannot
verify forecast provenance, source independence, real betting ROI or a fresh bet.
"""
import gzip
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from source_publish_guard import verify

MAX_HISTORY_FILES = 70
MAX_GZIP_INPUT_BYTES = 150_000
MAX_JSON_BYTES = 500_000
MAX_HISTORY_AGE = timedelta(days=14)
MAX_CANDIDATES = 100


def _utc(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_ARCHIVED_KICKOFF")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("INVALID_ARCHIVED_KICKOFF")
    return stamp.astimezone(timezone.utc)


def recover(root, now, *, max_candidates=MAX_CANDIDATES):
    """Return bounded provisional observations, all source conflicts preserved."""
    diag = {
        "schema": "football-king-free-score-history-recovery-v1",
        "status": "HOLD", "reason": "NO_VALID_ARCHIVED_SNAPSHOTS",
        "history_files_inspected": 0, "snapshots_valid": 0,
        "snapshots_rejected": 0, "finished_observations_considered": 0,
        "historical_finished_candidates": 0,
        "same_provider_repeated_observations_suppressed": 0,
        "single_source_only_not_independently_verified": True,
        "may_settle_only_prior_sealed_research_cases": True,
        "executed_api_queries": 0, "market_odds_executable": False,
        "production_recommendations": "DISABLED",
    }
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("NAIVE_RECOVERY_CLOCK")
    if type(max_candidates) is not int or not 0 <= max_candidates <= MAX_CANDIDATES:
        raise ValueError("INVALID_HISTORY_CANDIDATE_CAP")
    now = now.astimezone(timezone.utc)
    if not root or not Path(root).is_dir() or max_candidates == 0:
        return [], diag
    base = Path(root)
    paths = sorted(base.glob("20??/??/??/*.json.gz"), reverse=True)
    # Do not silently use an unbounded archive even when GitHub grows.
    if len(paths) > 2000:
        diag["reason"] = "TOO_MANY_HISTORY_FILES"
        return [], diag
    # Read recent names first; individual document timestamps are authoritative.
    seen = set()
    result = []
    for path in paths[:MAX_HISTORY_FILES]:
        diag["history_files_inspected"] += 1
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_GZIP_INPUT_BYTES:
                raise ValueError("UNSAFE_SOURCE_ARCHIVE")
            with gzip.open(path, "rb") as stream:
                raw = stream.read(MAX_JSON_BYTES + 1)
            if len(raw) > MAX_JSON_BYTES:
                raise ValueError("UNBOUNDED_FREE_SOURCE_GZIP")
            doc = json.loads(raw.decode("utf-8"))
            captured = verify(doc, now=now)
            if not timedelta(0) <= now - captured <= MAX_HISTORY_AGE:
                raise ValueError("HISTORY_OUTSIDE_RETENTION_WINDOW")
            diag["snapshots_valid"] += 1
        except (OSError, EOFError, UnicodeError, ValueError, TypeError, KeyError,
                OverflowError, gzip.BadGzipFile):
            diag["snapshots_rejected"] += 1
            continue
        for row in doc["sampled_fixtures"]:
            if row.get("status") != "FINISHED" or row.get("score_ft") is None:
                continue
            diag["finished_observations_considered"] += 1
            try:
                kickoff = _utc(row["kickoff_utc"])
                if (captured < kickoff + timedelta(minutes=100)
                        or now < kickoff + timedelta(minutes=120)):
                    continue
                # Distinct revised FT scores are NOT de-duplicated: preserve
                # them so build_index quarantines divergent outcomes.
                identity = (row["provider"], row["league"],
                            row["provider_event_id"], kickoff.isoformat(),
                            row["home"], row["away"], tuple(row["score_ft"]))
                if identity in seen:
                    diag["same_provider_repeated_observations_suppressed"] += 1
                    continue
                seen.add(identity)
                result.append({
                    "league": row["league"], "home": row["home"],
                    "away": row["away"], "kickoff_utc": kickoff.isoformat(),
                    "score_ft": list(row["score_ft"]), "status": "FINISHED",
                    "source_provider": row["provider"],
                    "independently_verified": False,
                })
                if len(result) >= max_candidates:
                    break
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
        if len(result) >= max_candidates:
            break
    diag["historical_finished_candidates"] = len(result)
    if diag["snapshots_valid"]:
        diag["status"] = "RESEARCH_ONLY"
        diag["reason"] = "ARCHIVED_PROVISIONAL_FINALS_ONLY"
    return result, diag
