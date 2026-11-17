"""Real archived-shadow source replay: old vs fixed sentinel, same current selector.

This is an OUTCOME-BLIND, post-hoc engineering A/B, not a new live or
independently attested model evaluation. Both arms use exactly the same
research_recommender.build() and archived source bytes; ONLY its sentinel
function is swapped for the original immutable Git blob vs current code.
No network, vendor price, result fetching, model refitting, or betting.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import zlib
import os
from pathlib import Path
import types

from . import home_favourite_sentinel as fixed
from . import research_recommender as recommender

SCHEMA = "football-king-home-bias-real-archive-ab-v1"
LEGACY_BLOB = "9e004db15e257bc58613410f26b92a82211e7f52"
MAX_COMPRESSED = 300_000
MAX_UNCOMPRESSED = 3_000_000


def _hold(reason, **kwargs):
    return {
        "schema": SCHEMA,
        "status": "HOLD", "reason": reason,
        "production_recommendations": "DISABLED",
        "positive_ev_verified": False, "model_promoted": False,
        "certified_prospective_samples": 0, "independent_source_attested": False,
        "historical_actual_betting_roi_verified": False,
        "sample_is_untouched_confirmatory": False,
        **kwargs,
    }


def _unique(pairs):
    d = {}
    for key, value in pairs:
        if key in d:
            raise ValueError("DUPLICATE_JSON_KEY")
        d[key] = value
    return d


def read_archive(filename, *, repo_root):
    path = (repo_root / filename)
    if (type(filename) is not str or not filename.startswith("shadow/")
            or not filename.endswith(".json.gz")
            or ".." in Path(filename).parts or path.is_symlink()
            or not path.is_file()):
        raise ValueError("INVALID_ARCHIVED_SHADOW_PATH")
    raw_zip = path.read_bytes()
    if len(raw_zip) > MAX_COMPRESSED:
        raise ValueError("ARCHIVE_COMPRESSED_TOO_LARGE")
    # gzip.decompress is safe here only because compressed and inflated
    # bounds are independently enforced by a bounded incremental stream.
    z = zlib.decompressobj(16 + zlib.MAX_WBITS)
    body = z.decompress(raw_zip, MAX_UNCOMPRESSED + 1)
    if (len(body) > MAX_UNCOMPRESSED or not z.eof or z.unconsumed_tail
            or z.unused_data or z.flush()):
        raise ValueError("ARCHIVE_TRUNCATED_TRAILING_OR_TOO_LARGE")
    data = json.loads(
        body, object_pairs_hook=_unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")),
    )
    if (type(data) is not dict or
            data.get("production_recommendations") != "DISABLED"
            or data.get("status") != "SHADOW_ONLY"
            or type(data.get("predictions")) is not list
            or len(data["predictions"]) > 1000):
        raise ValueError("NOT_AN_UNMODIFIED_SHADOW_OBSERVATION")
    now = recommender.timestamp(data["as_of_utc"]) + timedelta(minutes=5)
    return data, now, {
        "path": filename,
        "compressed_sha256": hashlib.sha256(raw_zip).hexdigest(),
        "original_json_sha256": hashlib.sha256(body).hexdigest(),
        "archived_as_of_utc": data["as_of_utc"],
        "counterfactual_evaluation_utc": now.isoformat(),
        "counterfactual_now_plus_5min_not_historical_execution_time": True,
        "input_record_count": len(data["predictions"]),
    }


def load_pinned_legacy_assess(repo_root):
    """Use the exact pre-fix Git blob, retained in repo for shallow-clone CI."""
    baseline = (repo_root / "ops" / "research_baselines" /
                "home_favourite_sentinel_9e004db.py")
    if baseline.is_symlink() or not baseline.is_file():
        raise ValueError("MISSING_PINNED_LEGACY_BASELINE")
    obj = baseline.read_bytes()
    # Git's blob identity is SHA1(b"blob <byte-length>\0" + bytes). Verify
    # the literal baseline source, not merely a hand-copied function name.
    digest = hashlib.sha1(
        (f"blob {len(obj)}\0".encode("ascii") + obj)).hexdigest()
    if (digest != LEGACY_BLOB or len(obj) > 10_000 or
            b"def assess(predictions):" not in obj or b"def _utc(" in obj):
        raise ValueError("LEGACY_SENTINEL_BLOB_DRIFT")
    legacy = types.ModuleType("pinned_legacy_home_bias_sentinel")
    exec(compile(obj, "<pinned-legacy-home-bias-Git-blob>", "exec"),
         legacy.__dict__)
    return legacy.assess


@contextmanager
def replace_only_sentinel(func):
    previous = recommender.assess_home_bias
    try:
        recommender.assess_home_bias = func
        yield
    finally:
        recommender.assess_home_bias = previous


def compare_one(data, now, legacy):
    snapshot = recommender.timestamp(data["as_of_utc"])
    pairing = {"status": "HOLD", "comparisons": [],
               "production_recommendations": "DISABLED"}
    status = {"status": "RESEARCH_ONLY",
              "production_recommendations": "DISABLED"}
    # Counterfactual: use current recommendation engine for BOTH arms.
    # The single intervention is the original vs repaired home-bias sentinel.
    with replace_only_sentinel(lambda predictions, **ignored: legacy(predictions)):
        old = recommender.build(data, pairing, status, now=now)
    new = recommender.build(data, pairing, status, now=now)
    legacy_s = legacy(data["predictions"])["by_league"]
    fixed_s = fixed.assess(
        data["predictions"], now=now, model_capture=snapshot)["by_league"]
    if (recommender.assess_home_bias is not fixed.assess
            or old["production_recommendations"] != "DISABLED"
            or new["production_recommendations"] != "DISABLED"
            or old["value_recommendation_count"] != 0
            or new["value_recommendation_count"] != 0
            or old["automatic_bets"] is not False
            or new["automatic_bets"] is not False):
        raise ValueError("UNSAFE_ABLATION_OR_PRODUCTION_OUTPUT")
    by_league = {}
    for league in sorted(legacy_s):
        a, b = legacy_s[league], fixed_s[league]
        by_league[league] = {
            "legacy_eligible_pre_match_claims": a["valid_distinct_pre_match_forecasts"],
            "fixed_time_valid_eligible": b["valid_distinct_pre_match_forecasts"],
            "removed_from_risk_denominator": (
                a["valid_distinct_pre_match_forecasts"] -
                b["valid_distinct_pre_match_forecasts"]),
            "legacy_home_top": a["home_top_forecasts"],
            "fixed_home_top": b["home_top_forecasts"],
            "legacy_quarantine_flag": a["home_favourite_concentration_review"],
            "fixed_quarantine_flag": b["home_favourite_concentration_review"],
        }
    return {
        "legacy_selector_status": old["status"],
        "fixed_selector_status": new["status"],
        "legacy_model_only_count": old["model_only_count"],
        "fixed_model_only_count": new["model_only_count"],
        "delta_fixed_minus_legacy_model_only": (
            new["model_only_count"] - old["model_only_count"]),
        "selection_not_approved_or_tradable": True,
        "by_league": by_league,
    }


def audit(paths, *, repo_root, legacy=None):
    if type(paths) is not list or not 1 <= len(paths) <= 10:
        return _hold("NO_ARCHIVES_OR_TOO_MANY")
    legacy = legacy or load_pinned_legacy_assess(repo_root)
    samples = []
    seen_sha = set()
    try:
        for name in paths:
            data, now, meta = read_archive(name, repo_root=repo_root)
            if meta["original_json_sha256"] in seen_sha:
                raise ValueError("DUPLICATED_ARCHIVED_SNAPSHOT")
            seen_sha.add(meta["original_json_sha256"])
            check = compare_one(data, now, legacy)
            samples.append({**meta, **check})
        return _hold(
            "RETROSPECTIVE_REAL_SNAPSHOT_SENTINEL_AB_ONLY",
            legacy_sentinel_git_blob_sha=LEGACY_BLOB,
            snapshots_checked=len(samples),
            source_bytes_were_unmodified=True,
            source_availability_at_original_time_independently_verified=False,
            historical_actual_observation_time_verified=False,
            comparison_isolated_to_sentinel_only=True,
            number_of_unique_scored_matches=0,
            independent_match_results_scored=0,
            results=samples,
        )
    except (KeyError, ValueError, TypeError, OSError, OverflowError, EOFError,
            json.JSONDecodeError, zlib.error):
        return _hold(
            "REAL_ARCHIVED_AB_BLOCKED",
            completed_before_first_block=len(samples),
            # No partial scoreboard; only source digests already validated.
        )


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", nargs="+", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--repo-root", default=".")
    args = p.parse_args(argv)
    root = Path(args.repo_root).resolve()
    report = audit(args.archive, repo_root=root)
    body = (json.dumps(report, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), allow_nan=False)+"\n").encode()
    target = Path(args.output)
    if target.exists() or target.is_symlink():
        raise ValueError("CANNOT_OVERWRITE_ARCHIVED_AB_OUTPUT")
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(body)
    print("HOME_BIAS_REAL_ARCHIVED_AB", body.decode().strip())
    return 0 if report["reason"] == "RETROSPECTIVE_REAL_SNAPSHOT_SENTINEL_AB_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
