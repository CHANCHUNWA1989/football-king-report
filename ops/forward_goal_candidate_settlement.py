"""Research-only, read-only candidate settlement of a PINNED future goal cohort.

Never promotes self-reported provider records to independently verified finals.
Two distinct provider name strings and matching scores are necessary but NOT
sufficient for independent authentication. Any conflicting score is HOLD.
No original forecast can be rewritten or removed and no betting EV is computed.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import re

from .forward_goal_shadow_cohort_seal import verify as verify_snapshot, _instant

SCHEMA = "football-king-forward-goal-readonly-candidate-settlement-v1"
MIN_GAME_ELAPSED = timedelta(minutes=90)
MAX_OBSERVATIONS = 1000
MARKETS = ("over25", "btts")


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _name(value, reason):
    _require(type(value) is str and 0 < len(value.strip()) <= 140
             and value == value.strip(), reason)
    return value


def _digest(value):
    _require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
             "INVALID_PINNED_DIGEST")
    return value


def _time(value):
    return _instant(value)


def _goal(value):
    _require(type(value) is int and 0 <= value <= 25,
             "INVALID_FINAL_SCORE")
    return value


def _score(p, y):
    return ((p-y)**2,
            -(y*math.log(max(1e-15,min(1-1e-15,p))) +
              (1-y)*math.log(max(1e-15,min(1-1e-15,1-p)))))


def audit(snapshot, observations, *, expected_snapshot_sha256, expected_capture_id, now=None):
    """Score all and only eligible future fixtures in the exact pinned snapshot.

    Caller must compare artifact ZIP with GitHub API separately; the passed
    SHA is an external selection parameter, not cryptographic certification.
    """
    _digest(expected_snapshot_sha256)
    _name(expected_capture_id, "INVALID_EXPECTED_CAPTURE_ID")
    _require(isinstance(snapshot, dict), "INVALID_SNAPSHOT")
    _require(snapshot.get("sha256") == expected_snapshot_sha256,
             "PINNED_SNAPSHOT_HASH_MISMATCH")
    verify_snapshot(snapshot)
    body = snapshot["payload"]
    _require(body.get("source", {}).get("source_capture_id") == expected_capture_id,
             "CAPTURE_RUN_ID_MISMATCH")
    _require(body.get("status") == "HOLD"
             and body.get("production_recommendations") == "DISABLED"
             and body.get("certified_prospective_samples") == 0,
             "UNSAFE_OR_NONPROSPECTIVE_SNAPSHOT")
    _require(type(observations) is list and len(observations) <= MAX_OBSERVATIONS,
             "INVALID_RESULT_OBSERVATIONS")
    now = now or datetime.now(timezone.utc)
    _require(isinstance(now, datetime) and now.tzinfo is not None
             and now.utcoffset() is not None, "INVALID_AUDIT_CLOCK")
    now = now.astimezone(timezone.utc)
    _require(_time(body["captured_by_local_runner_utc_self_reported"]) <= now,
             "SNAPSHOT_CAPTURE_AFTER_AUDIT")

    by_fixture = {}
    for row in body["fixtures"]:
        ident = row["fixture"]["fixture_id"]
        _require(ident not in by_fixture, "DUPLICATE_SNAPSHOT_FIXTURE")
        by_fixture[ident] = row
    _require(len(by_fixture) == body["source_fixture_universe_count"],
             "SNAPSHOT_COHORT_COUNT_MISMATCH")

    obs_by_fixture = defaultdict(list)
    observed_identifiers = set()
    native_event_scope = {}
    for o in observations:
        required = {
            "fixture_id", "provider_namespace", "provider_fixture_id",
            "captured_utc", "raw_response_sha256", "status", "home_goals",
            "away_goals",
        }
        _require(type(o) is dict and set(o) == required,
                 "INVALID_RESULT_OBSERVATION_CONTRACT")
        fid = _name(o["fixture_id"], "INVALID_RESULT_FIXTURE_ID")
        _require(fid in by_fixture, "RESULT_FOR_UNLISTED_FIXTURE")
        provider = _name(o["provider_namespace"], "INVALID_PROVIDER_NAMESPACE")
        provider_id = _name(o["provider_fixture_id"], "INVALID_PROVIDER_EVENT_ID")
        _digest(o["raw_response_sha256"])
        _require(o["status"] == "FT", "RESULT_NOT_90_MINUTE_FINAL")
        gh, ga = _goal(o["home_goals"]), _goal(o["away_goals"])
        captured = _time(o["captured_utc"])
        kickoff = _time(by_fixture[fid]["fixture"]["kickoff_utc"])
        _require(kickoff + MIN_GAME_ELAPSED <= captured <= now,
                 "RESULT_TIME_PREMATURE_OR_IN_FUTURE")
        unique = (fid, provider)
        _require(unique not in observed_identifiers,
                 "DUPLICATE_RESULT_PROVIDER_FOR_FIXTURE")
        # A single provider-native event ID must not be re-used to provide
        # results for two separate frozen fixtures.
        native_key = (provider, provider_id)
        previous_scope = native_event_scope.get(native_key)
        _require(previous_scope is None or previous_scope == fid,
                 "PROVIDER_NATIVE_EVENT_REUSED_ACROSS_FIXTURES")
        native_event_scope[native_key] = fid
        observed_identifiers.add(unique)
        obs_by_fixture[fid].append((provider, provider_id, captured, o["raw_response_sha256"], gh, ga))

    pooled = {m: {"n":0, "a_brier":0.0, "blend_brier":0.0,
                  "prior_brier":0.0,
                  "a_logloss":0.0, "blend_logloss":0.0,
                  "prior_logloss":0.0,
                  "observed_positive":0} for m in MARKETS}
    counts = defaultdict(int)
    rows = []
    for fid in sorted(by_fixture):
        f = by_fixture[fid]
        kickoff = _time(f["fixture"]["kickoff_utc"])
        observations_for_fixture = obs_by_fixture[fid]
        settlement = "MATCH_NOT_MATURED" if now < kickoff+MIN_GAME_ELAPSED else "WAITING_TWO_SOURCES"
        candidate = None
        if now >= kickoff+MIN_GAME_ELAPSED:
            if len(observations_for_fixture) == 1:
                settlement = "WAITING_SECOND_PROVIDER"
            elif len(observations_for_fixture) >= 2:
                scores = {(x[4], x[5]) for x in observations_for_fixture}
                hashes = [x[3] for x in observations_for_fixture]
                if len(scores) != 1:
                    settlement = "CONFLICTING_FINAL_SCORES_HOLD"
                elif len(set(hashes)) != len(hashes):
                    settlement = "SAME_RAW_EVIDENCE_HOLD"
                else:
                    settlement = "MATCHED_TWO_PROVIDER_NAMES_UNVERIFIED"
                    candidate = list(next(iter(scores)))
        row = {
            "fixture_id": fid,
            "kickoff_utc": f["fixture"]["kickoff_utc"],
            "forecast_state": f["state"],
            "settlement_state": settlement,
            "provider_name_count": len(observations_for_fixture),
            "candidate_score_ft": candidate,
            "markets": {},
        }
        counts[settlement] += 1
        if candidate is not None and f["state"] == "UNVERIFIED_PREMATCH_RESEARCH_FORECAST":
            h,g = candidate
            y = {"over25": int(h+g>2), "btts": int(h>0 and g>0)}
            for market in MARKETS:
                p = f[market]
                a = p["original"]
                blend = p["exploratory_75_25_blend"]
                prior = p["training_only_prior"]
                sc_a = _score(a,y[market])
                sc_b = _score(blend,y[market])
                sc_prior = _score(prior,y[market])
                row["markets"][market] = {
                    "actual_binary": y[market],
                    "original_brier_contribution": round(sc_a[0],10),
                    "blend_brier_contribution": round(sc_b[0],10),
                    "training_only_prior_brier_contribution": round(sc_prior[0],10),
                }
                agg = pooled[market]
                agg["n"] += 1
                agg["a_brier"] += sc_a[0]
                agg["blend_brier"] += sc_b[0]
                agg["prior_brier"] += sc_prior[0]
                agg["a_logloss"] += sc_a[1]
                agg["blend_logloss"] += sc_b[1]
                agg["prior_logloss"] += sc_prior[1]
                agg["observed_positive"] += y[market]
        rows.append(row)
    summary = {}
    for market in MARKETS:
        v = pooled[market]
        n = v["n"]
        summary[market] = {
            "candidate_scored": n,
            "original_brier": round(v["a_brier"]/n,8) if n else None,
            "blend_brier": round(v["blend_brier"]/n,8) if n else None,
            "training_only_prior_brier": round(v["prior_brier"]/n,8) if n else None,
            "original_logloss": round(v["a_logloss"]/n,8) if n else None,
            "blend_logloss": round(v["blend_logloss"]/n,8) if n else None,
            "training_only_prior_logloss": round(v["prior_logloss"]/n,8) if n else None,
            "observed_positive_rate": round(v["observed_positive"]/n,8) if n else None,
            "blend_brier_improvement_descriptive_only": (
                round((v["a_brier"]-v["blend_brier"])/n,8) if n else None),
        }
    # This snapshot has a frozen nine-game universe. Partial matched cases are
    # useful for debugging but NOT an entire-cohort calibration claim.
    complete = (len(rows) == 9
                and summary["over25"]["candidate_scored"] == len(rows)
                and summary["btts"]["candidate_scored"] == len(rows))
    return {
        "schema": SCHEMA,
        "status": "HOLD",
        "pinned_unverified_snapshot_sha256": expected_snapshot_sha256,
        "capture_id": expected_capture_id,
        "as_of_utc": now.isoformat(),
        "entire_original_cohort_retained": len(rows),
        "unmatched_or_unscored_cases_retained": (
            len(rows)-summary["over25"]["candidate_scored"]),
        "candidate_provider_agreements_only": counts.get("MATCHED_TWO_PROVIDER_NAMES_UNVERIFIED", 0),
        "certified_independent_forward_cases": 0,
        "two_provider_names_are_not_authenticated_independent_sources": True,
        "snapshot_artifact_sha_verified_against_github_in_this_module": False,
        "official_final_result_independently_verified": False,
        "quote_pricing_available": False,
        "positive_ev_verified": False,
        "automated_betting_enabled": False,
        "eligible_for_model_promotion": False,
        "production_recommendations": "DISABLED",
        "fixture_states": dict(sorted(counts.items())),
        "paired_market_diagnostics": summary,
        "paired_market_diagnostics_are_partial_unless_full_cohort": not complete,
        "full_nine_fixture_cohort_scored": complete,
        "full_cohort_market_metrics_unverified": summary if complete else None,
        "full_cohort_independently_certified": False,
        "fixtures": rows,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--observations", required=True)
    parser.add_argument("--snapshot-sha256", required=True)
    parser.add_argument("--capture-id", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    def read(path):
        return json.loads(Path(path).read_text(encoding="utf-8"))
    report = audit(read(args.snapshot), read(args.observations),
                   expected_snapshot_sha256=args.snapshot_sha256,
                   expected_capture_id=args.capture_id)
    target = Path(args.output)
    _require(not target.exists() and not target.is_symlink(),
             "REFUSE_TO_OVERWRITE_SETTLEMENT_REPORT")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as out:
        json.dump(report, out, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        out.write("\n")
    print("FORWARD_GOAL_CANDIDATE_SETTLEMENT",
          report["entire_original_cohort_retained"],
          report["candidate_provider_agreements_only"],
          report["status"], report["production_recommendations"])


if __name__ == "__main__":
    main()
