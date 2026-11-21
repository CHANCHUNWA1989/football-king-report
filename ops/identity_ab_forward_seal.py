"""Pre-kickoff immutable A/B forecast records, one file per provider-native fixture.

No outcomes or executable bookmaker lines. The source snapshot was captured once
by a GitHub runner, not independently notarized. The files are PUBLIC research
artifacts with probabilistic estimates only; Git history is NOT WORM storage.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

SCHEMA = "football-king-prospective-identity-ab-forecast-v1"
INDEX_SCHEMA = "football-king-prospective-identity-ab-index-v1"
ID_RE = re.compile(r"openligadb:([1-9][0-9]{0,10})\Z")
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
MAX_FIXTURES = 50


class SealError(ValueError):
    """Fixed failure code; do not print untrusted identity or file contents."""


def _require(ok, code):
    if not ok:
        raise SealError(code)


def _date(value):
    _require(type(value) is str and len(value) <= 50, "INVALID_CAPTURE_TIME")
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        _require(instant.tzinfo is not None and instant.utcoffset() is not None,
                 "INVALID_CAPTURE_TIME")
        return instant.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        raise SealError("INVALID_CAPTURE_TIME") from None


def _vector(value):
    if value is None:
        return None
    _require(type(value) is list and len(value) == 3
             and all(type(p) in (int, float) and math.isfinite(p)
                     and 0 <= p <= 1 for p in value)
             and abs(sum(value) - 1) <= 3e-6, "INVALID_FORECAST_PROBABILITIES")
    return [float(p) for p in value]


def _bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def records(probe, *, received_utc, source_commit, run_id, attempt):
    """Return sealed, sorted record bytes; fail all together on contradictions."""
    _require(type(probe) is dict and type(probe.get("ab")) is dict,
             "INVALID_PROSPECTIVE_REPORT")
    ab = probe["ab"]
    now = _date(received_utc)
    _require(probe.get("provider") == "OpenLigaDB"
             and probe.get("status") == "RESEARCH_ONLY"
             and ab.get("status") == "RESEARCH_ONLY"
             and ab.get("league") == "bundesliga"
             and _date(ab.get("as_of_utc")) == now
             and ab.get("same_input_and_as_of_for_both_models") is True
             and ab.get("future_result_input_used") is False
             and ab.get("model_accuracy_improved_proven") is False
             and ab.get("market_benchmark_beaten") is False
             and ab.get("production_recommendations") == "DISABLED"
             and probe.get("production_recommendations") == "DISABLED"
             and probe.get("certified_case_count") == 0
             and probe.get("prediction_accuracy_improved_proven") is False
             and probe.get("positive_ev_verified") is False
             and probe.get("provider_capture_authenticated") is False
             and type(source_commit) is str and SHA_RE.fullmatch(source_commit)
             and ab.get("candidate_source_commit") == source_commit
             and type(run_id) is str and re.fullmatch(r"[1-9][0-9]{0,19}",run_id)
             and type(attempt) is str and re.fullmatch(r"[1-9][0-9]{0,5}",attempt),
             "UNTRUSTED_PROSPECTIVE_REPORT")
    source_sha = probe.get("raw_source_sha256")
    input_sha = ab.get("input_canonical_sha256")
    legacy_sha = ab.get("frozen_legacy_source_blob_sha1")
    _require(all(type(x) is str and re.fullmatch(p, x) for x,p in
                 ((source_sha, DIGEST_RE), (input_sha,DIGEST_RE),
                  (legacy_sha,SHA_RE))), "INVALID_SOURCE_DIGEST")
    counts = ab.get("counts")
    _require(type(counts) is dict, "INVALID_FORECAST_COUNTS")
    paired = ab.get("paired")
    a_only = ab.get("legacy_only")
    b_only = ab.get("candidate_only")
    _require(all(type(x) is list for x in (paired,a_only,b_only))
             and 0 < len(paired)+len(a_only)+len(b_only) <= MAX_FIXTURES
             and len(paired) == counts.get("paired")
             and len(a_only) == counts.get("legacy_only")
             and len(b_only) == counts.get("candidate_only")
             and counts.get("legacy") == len(paired)+len(a_only)
             and counts.get("candidate") == len(paired)+len(b_only),
             "INVALID_FORECAST_COUNTS")
    drafts = []
    for status, cases in (("PAIRED", paired),("LEGACY_ONLY",a_only),
                          ("CANDIDATE_ONLY",b_only)):
        for case in cases:
            _require(type(case) is dict, "INVALID_FORECAST_ITEM")
            eid, kickoff = case.get("event_id"), case.get("kickoff_utc")
            _require(type(eid) is str and ID_RE.fullmatch(eid) is not None
                     and _date(kickoff) > now + timedelta(minutes=60),
                     "NOT_GENUINELY_PREKICKOFF")
            home, away = case.get("home"), case.get("away")
            if status == "PAIRED":
                _require(type(home) is str and 0 < len(home) < 110
                         and type(away) is str and 0 < len(away) < 110
                         and home != away
                         and case.get("comparison_has_result_outcome") is False,
                         "UNSAFE_FORECAST_ITEM")
                old = _vector(case.get("legacy_1x2"))
                new = _vector(case.get("candidate_1x2"))
                _require(old is not None and new is not None,
                         "INVALID_FORECAST_PROBABILITIES")
                _require(case.get("training_cutoff_local_day") is not None,
                         "INVALID_TRAINING_CUTOFF")
            else:
                _require(set(case) == {"event_id","kickoff_utc"},
                         "UNSAFE_UNPAIRED_ITEM")
                old, new, home, away = None, None, None, None
            native = ID_RE.fullmatch(eid).group(1)
            doc = {
                "schema": SCHEMA, "status": "SHADOW_ONLY_UNVERIFIED",
                "provider": "OpenLigaDB", "provider_native_event_id": native,
                "event_id": eid, "league": "bundesliga",
                "home": home, "away": away,
                "scheduled_kickoff_utc": _date(kickoff).isoformat(),
                "source_response_received_utc": now.isoformat(),
                "forecast_created_before_scheduled_kickoff": True,
                "forecast_horizon_at_capture_minutes":
                    int((_date(kickoff)-now).total_seconds()//60),
                "research_coverage": status,
                "legacy_1x2": old, "candidate_1x2": new,
                "source_response_sha256": source_sha,
                "normalized_model_input_sha256": input_sha,
                "frozen_legacy_source_blob_sha1": legacy_sha,
                "candidate_source_commit": source_commit,
                "github_run_id": run_id, "github_run_attempt": attempt,
                "source_independently_authenticated": False,
                "github_run_timestamp_is_not_cryptographic_notarization": True,
                "regulation_time_result_verified": False,
                "actual_kickoff_authenticated": False,
                "market_odds_verified": False, "forecast_calibrated": False,
                "model_accuracy_improved_proven": False,
                "positive_ev_verified": False,
                "certified_case_count": 0,
                "production_recommendations": "DISABLED",
            }
            _require(not any(k in doc for k in
                     ("score_ft","result","historical_outcome","settlement")),
                     "OUTCOME_IN_PROSPECTIVE_ARCHIVE")
            name = native + ".json"
            drafts.append((name, _bytes(doc)))
    names = [name for name,_ in drafts]
    _require(len(names) == len(set(names)), "DUPLICATE_ARCHIVED_EVENT")
    return dict(sorted(drafts))


def create_local_archive(directory, probe, *, received_utc, source_commit,
                         run_id, attempt):
    """0700 private runner temp; create-only 0600 files with final readback."""
    root = Path(directory)
    _require(root.is_absolute() and not root.exists()
             and not any(parent.is_symlink() for parent in root.parents)
             and root.parent.is_dir() and not root.parent.is_symlink(),
             "UNSAFE_ARCHIVE_OUTPUT")
    entries = records(probe, received_utc=received_utc,
                      source_commit=source_commit, run_id=run_id,attempt=attempt)
    index = {
        "schema": INDEX_SCHEMA, "status":"SHADOW_ONLY_UNVERIFIED",
        "source_response_received_utc":_date(received_utc).isoformat(),
        "source_response_sha256":probe["raw_source_sha256"],
        "source_commit":source_commit,
        "github_run_id":run_id, "github_run_attempt":attempt,
        "record_count":len(entries),
        "record_sha256":{name:hashlib.sha256(raw).hexdigest()
                         for name,raw in entries.items()},
        "all_forecasts_are_pre_match_and_unsettled": True,
        "original_source_authenticity_verified":False,
        "independently_verified_result_count":0,
        "production_recommendations":"DISABLED",
    }
    entries["index.json"] = _bytes(index)
    root.mkdir(mode=0o700)
    try:
        for name, raw in sorted(entries.items()):
            path=root / name
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL
                       |getattr(os,"O_NOFOLLOW",0),0o600)
            with os.fdopen(fd,"wb") as fp:
                fp.write(raw)
                fp.flush()
                os.fsync(fp.fileno())
            st=path.lstat()
            _require(stat.S_ISREG(st.st_mode) and st.st_nlink==1
                     and st.st_mode & 0o077 == 0
                     and path.read_bytes()==raw,
                     "LOCAL_ARCHIVE_READBACK_CHANGED")
    except Exception:
        for name in entries:
            try: (root/name).unlink(missing_ok=True)
            except OSError: pass
        try: root.rmdir()
        except OSError: pass
        raise
    return index
