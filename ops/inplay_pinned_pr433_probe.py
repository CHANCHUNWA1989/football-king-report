"""Pinned PR #433 synthetic invocation probe; NEVER a live match forecast.

A successful run observes the real predict() code from the exact frozen PR433
Git commit and two expected Git blob bytes in a local checkout. Git blob
agreement is NOT external publisher authentication, signed time, venue/fixture
evidence, model calibration, or certification for betting. No live network API.
"""
import argparse
import hashlib
import importlib
import inspect
import json
import stat
import subprocess
import sys
from pathlib import Path

from inplay_pair_execution_observation import observe_local

SCHEMA="football-king-inplay-pinned-PR433-smoke-v1"
PINNED_COMMIT="f2e92bdfeb2c36ebf1efeb708153303a607318a6"
PINNED_BLOBS={
    "ops/inplay_state_challenger_vnext.py":"d664d7cc561426956842f54901b581e27da04fb5",
    "ops/score_distribution_vnext.py":"ef35e05e999a9a894bac25428021f350e43b4b97",
}


def _hold(reason):
    return {
        "schema":SCHEMA, "status":"HOLD", "reason":reason,
        "production_recommendations":"DISABLED",
        "genuine_pr433_execution_observed_locally":False,
        "pinned_source_blobs_matched":False,
        "candidate_source_publisher_authenticated":False,
        "externally_witnessed":False,
        "point_in_time_data_authenticated":False,
        "formal_model_comparison_allowed":False,
        "positive_ev_verified":False,
        "certified_paired_samples":0,
        "recommendation":None, "roi":None,
    }


def _git_blob_sha1(raw):
    header=b"blob "+str(len(raw)).encode("ascii")+b"\x00"
    return hashlib.sha1(header+raw).hexdigest()


def _validate_tree(root):
    if not isinstance(root,Path) or not root.is_dir():
        raise ValueError("MISSING_CANDIDATE_CHECKOUT")
    try:
        git=subprocess.run(["git","-C",str(root),"rev-parse","HEAD"],
                           capture_output=True,text=True,check=True,timeout=10)
    except (OSError,subprocess.CalledProcessError,subprocess.TimeoutExpired):
        raise ValueError("PINNED_HEAD_UNVERIFIABLE") from None
    if git.stdout.strip()!=PINNED_COMMIT:
        raise ValueError("PINNED_HEAD_MISMATCH")
    for rel,expected in PINNED_BLOBS.items():
        filename=root/rel
        try:
            # Reject symlinks and anything other than a normal readable file.
            mode=filename.lstat().st_mode
            if not stat.S_ISREG(mode):
                raise ValueError("SOURCE_NOT_REGULAR_FILE")
            raw=filename.read_bytes()
        except (OSError,PermissionError):
            raise ValueError("SOURCE_NOT_REGULAR_FILE") from None
        if _git_blob_sha1(raw)!=expected:
            raise ValueError("SOURCE_BLOB_MISMATCH")
    return root/"ops"


def _inputs():
    """Artificial 1-1 halftime fixture, *not* River Plate or any real case."""
    fixture="synthetic_pr433_game"
    ko="2026-11-23T00:00:00Z"
    clock="2026-11-23T00:52:10Z"
    prematch="2026-11-22T23:30:00Z"
    case={
        "fixture":{"fixture_id":fixture,"home_id":"synthetic_home",
                   "away_id":"synthetic_away","kickoff_utc":ko},
        "prematch":{"home_goals_per_90":1.5,"away_goals_per_90":1.1,
                    "generated_utc":prematch,
                    "origin":"UNATTESTED_RESEARCH_ASSUMPTION"},
        "state":{"fixture_id":fixture,"observed_utc":"2026-11-23T00:52:00Z",
                 "as_of_utc":clock,"match_status":"HALF_TIME",
                 "elapsed_regulation_minutes":45,"home_goals":1,
                 "away_goals":1,"home_red_cards":0,"away_red_cards":0}}
    snapshot={
        "fixture_id":fixture,"kickoff_utc":ko,"decision_utc":clock,
        "minute_elapsed":45,"score_home":1,"score_away":1,
        "red_home":0,"red_away":0,
        "prematch":{"fixture_id":fixture,"model_id":"synthetic_prior_unverified",
                    "forecast_utc":prematch,"inputs_available_utc":"2026-11-22T23:29:00Z",
                    "expected_home_goals":1.5,"expected_away_goals":1.1,
                    "input_sha256":"a"*64,"production_recommendations":"DISABLED",
                    "calibrated":False},
        "event_consensus":{
            "status":"RESEARCH_ONLY","fixture_id":fixture,"decision_utc":clock,
            "score_home":1,"score_away":1,
            "active_red_cards":{"HOME":0,"AWAY":0},
            "production_recommendations":"DISABLED",
            "model_scoring_eligible":False,"source_authenticated":False,
            "source_independence_verified":False,
            "evidence_input_sha256":"b"*64}}
    return case,snapshot


def _load_pinned(root_ops):
    # Reject preloaded/hijacked names before import. Run once in a clean CI
    # Python process so neither global module namespace comes from elsewhere.
    names=("inplay_state_challenger_vnext","score_distribution_vnext")
    if any(name in sys.modules for name in names):
        raise ValueError("CANDIDATE_MODULE_ALREADY_IMPORTED")
    import_dir=str(root_ops.resolve())
    sys.path.insert(0,import_dir)
    try:
        module=importlib.import_module(names[0])
        dep=importlib.import_module(names[1])
        if (Path(module.__file__).resolve()!=root_ops.joinpath(names[0]+".py").resolve()
                or Path(dep.__file__).resolve()!=root_ops.joinpath(names[1]+".py").resolve()
                or module.predict.__module__ != names[0]
                or Path(inspect.getfile(module.predict)).resolve()!=Path(module.__file__).resolve()):
            raise ValueError("PINNED_CANDIDATE_IMPORT_MISMATCH")
        return module.predict
    finally:
        sys.path.remove(import_dir)


def run_pinned(root):
    """Observe *actual pinned callable* once using synthetic inputs only.

    This is an in-process code / byte identity exercise. It cannot prove
    upstream authorship, actual live run, real data, or external timestamp.
    """
    try:
        source_ops=_validate_tree(Path(root))
    except (ValueError,TypeError,OSError):
        return _hold("PINNED_CHECKOUT_MISMATCH")
    try:
        func=_load_pinned(source_ops)
    except (ValueError,ImportError,AttributeError,TypeError,OSError):
        return _hold("CANDIDATE_IMPORT_FAILED_OR_UNTRUSTED")
    case,snapshot=_inputs()
    observed=observe_local(case,snapshot,func)
    if (observed["status"]!="RESEARCH_ONLY"
            or observed["local_callback_invocation_count"]!=1
            or not observed["callback_return_observed_in_process"]):
        return _hold("PINNED_CALL_OUTPUT_FAILED_AUDIT")
    return {**_hold("PINNED_IN_PROCESS_EXECUTION_ONLY"),
            "status":"RESEARCH_ONLY",
            "reason":"PINNED_CODE_INVOKED_ON_SYNTHETIC_CASE_NOT_REAL_SPORTS_EVIDENCE",
            "genuine_pr433_execution_observed_locally":True,
            "pinned_source_blobs_matched":True,
            "pinned_repository_commit":PINNED_COMMIT,
            "candidate_source_blob_sha1":PINNED_BLOBS["ops/inplay_state_challenger_vnext.py"],
            "dependency_source_blob_sha1":PINNED_BLOBS["ops/score_distribution_vnext.py"],
            "local_execution_receipt_sha256_unattested":observed["output_sha256_unattested"],
            "synthetic_fixture_id":case["fixture"]["fixture_id"],
            "comparison":observed["comparison"],
            "synthetic_only":True,
            "candidate_not_in_main":True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-root",required=True)
    args=parser.parse_args()
    result=run_pinned(Path(args.candidate_root))
    print(json.dumps(result,ensure_ascii=False,sort_keys=True,allow_nan=False))
    raise SystemExit(0 if result["status"]=="RESEARCH_ONLY" else 2)


if __name__=="__main__":
    main()
