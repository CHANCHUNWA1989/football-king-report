"""Fail-closed FORWARD-ONLY UEFA 1X2 research candidate screen.

Strictly filters genuine *existing* A / Poisson / DC pre-match snapshot
without changing the frozen probabilities or fitting on subsequent results.
No betting promotion: fresh dates or three-model agreement do not prove
source authenticity, calibrated probabilities, executable odds, or EV.

Version-1 cutoffs (14 source days, 10 minute kickoff buffer, 20 p.p. model
disagreement) are explicitly research policy constants, not backtest winners.
A heldout past fixture can be inspected only as a diagnostic; it must never
receive a new 'prospective candidate' claim.
"""
from datetime import datetime, date, timedelta, timezone
import json
import math

SCHEMA = "football-king-forward-three-model-screen-v1"
SOURCE_SCHEMA = "football-king-real-20261115-unl-three-model-trial-v1"
MAX_SOURCE_AGE_DAYS = 14
KICKOFF_BUFFER = timedelta(minutes=10)
MAX_VOTE_SPREAD = 0.20
MAX_OBSERVATIONS = 50
NAMES = ("original_a_algorithm_1x2",
         "real_penaltyblog_poisson_1x2",
         "real_penaltyblog_dixon_coles_1x2")
DIRECTIONS = ("HOME", "DRAW", "AWAY")


def _time(raw):
    if type(raw) is not str or len(raw) > 64:
        raise ValueError("INVALID_FIXED_CLOCK")
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("INVALID_FIXED_CLOCK")
    return dt.astimezone(timezone.utc)


def _date(raw):
    if type(raw) is not str or len(raw) != 10:
        raise ValueError("INVALID_SOURCE_RESULT_DATE")
    return date.fromisoformat(raw)


def _prob(p):
    if type(p) is not list or len(p) != 3:
        raise ValueError("INVALID_PREMATCH_VECTOR")
    if any(type(x) not in (float, int) or not math.isfinite(x)
           or not 0 <= x <= 1 for x in p):
        raise ValueError("INVALID_PREMATCH_VECTOR")
    if abs(sum(p) - 1) > 0.00001:
        raise ValueError("INVALID_PREMATCH_VECTOR")
    return p


def _report(reason, **more):
    return {
        "schema": SCHEMA,
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "positive_ev_verified": False,
        "model_promoted": False,
        "certified_prospective_samples": 0,
        "source_publisher_authenticated": False,
        "historical_results_independently_timestamped": False,
        "bookmaker_price_independently_executable": False,
        "reason": reason, **more,
    }


def screen(snapshot, *, observed_at=None):
    """Present candidates only when future, fresh and unambiguous, never BETS.

    Use the frozen snapshot's captured time as the screening decision moment,
    but independently require observed_at to be before kickoff if given.
    Supplying a past observed_at can never retroactively certify custody.
    """
    if (type(snapshot) is not dict or
            snapshot.get("schema") != SOURCE_SCHEMA or
            snapshot.get("status") != "HOLD" or
            snapshot.get("production_recommendations") != "DISABLED" or
            snapshot.get("positive_ev_verified") is not False or
            snapshot.get("certified_prospective_samples") != 0 or
            snapshot.get("published_result_times_verified") is not False or
            snapshot.get("genuine_source_authenticity_verified") is not False or
            snapshot.get("original_a_is_adapted_club_algorithm_not_native_uefa_producer") is not True):
        return _report("SOURCE_FORECAST_NOT_TRUSTED_FOR_RESEARCH_SCREEN")
    records = snapshot.get("observations")
    if type(records) is not list or not 0 < len(records) <= MAX_OBSERVATIONS:
        return _report("INVALID_REAL_RESEARCH_COHORT")
    try:
        captured = _time(snapshot["dataset_fetched_utc"])
        latest_date = _date(snapshot["dataset_max_result_date"])
        external = datetime.now(timezone.utc) if observed_at is None else observed_at
        if (type(external) is not datetime or external.tzinfo is None
                or external.utcoffset() is None):
            raise ValueError("INVALID_ASSESSMENT_CLOCK")
        external = external.astimezone(timezone.utc)
        seen = set()
        output = []
        for row in records:
            if type(row) is not dict or not all(
                    type(row.get(k)) is str and row[k] for k in
                    ("fixture", "home", "away", "kickoff_utc")):
                raise ValueError("INVALID_SOURCE_MATCH_IDENTITY")
            if row["fixture"] in seen or row["home"] == row["away"]:
                raise ValueError("DUPLICATE_OR_CONFLICTED_MATCH")
            seen.add(row["fixture"])
            kickoff = _time(row["kickoff_utc"])
            issues = []
            start_date_age = (captured.date() - latest_date).days
            if not 0 <= start_date_age <= MAX_SOURCE_AGE_DAYS:
                issues.append("SOURCE_HISTORY_STALE_OR_FROM_FUTURE")
            if captured >= kickoff - KICKOFF_BUFFER:
                issues.append("SOURCE_NOT_PREMATCH")
            if external >= kickoff - KICKOFF_BUFFER:
                issues.append("ASSESSMENT_NOT_PREMATCH")
            if row.get("status") != "UNVERIFIED_PREMATCH_PROBABILITIES":
                issues.append("THREE_MODELS_NOT_COMPLETED")
                votes = []
            else:
                a = _time(row["a_computed_utc_unattested"])
                finished = _time(row["models_completed_utc_unattested"])
                if not captured <= a <= finished < kickoff - KICKOFF_BUFFER:
                    issues.append("MODEL_CLOCK_NOT_BEFORE_KICKOFF")
                if finished > external + timedelta(minutes=1):
                    issues.append("FORECAST_COMPLETION_IN_FUTURE")
                if row.get("no_uefa_native_event_id_claimed") is not True:
                    issues.append("INVALID_NATIVE_IDENTITY_DISCLOSURE")
                vectors = [_prob(row[key]) for key in NAMES]
                votes = []
                for v in vectors:
                    highest = max(v)
                    leaders = [i for i, value in enumerate(v)
                               if abs(value - highest) < 1e-9]
                    votes.append(leaders[0] if len(leaders) == 1 else None)
                if None in votes or len(set(votes)) != 1:
                    issues.append("MODEL_TOP_DIRECTION_CONFLICT_OR_TIE")
                else:
                    index = votes[0]
                    if (max(v[index] for v in vectors) -
                            min(v[index] for v in vectors) > MAX_VOTE_SPREAD):
                        issues.append("TOP_PROBABILITY_SPREAD_ABOVE_20PP")
            output.append({
                "fixture": row["fixture"],
                "home": row["home"], "away": row["away"],
                "kickoff_utc": kickoff.isoformat(),
                "eligibility": (
                    "UNVERIFIED_RESEARCH_CANDIDATE" if not issues
                    else "REJECTED_BY_RESEARCH_SCREEN"),
                "research_blockers": sorted(set(issues)),
                "consensus_direction": (
                    DIRECTIONS[votes[0]]
                    if len(votes) == 3 and votes[0] is not None
                    and len(set(votes)) == 1 else None),
            })
        return _report(
            "UNVERIFIED_FORWARD_SCREEN_REQUIRES_FRESH_INDEPENDENT_EVIDENCE",
            examined_fixture_count=len(records),
            unverified_candidate_count=sum(
                x["eligibility"] == "UNVERIFIED_RESEARCH_CANDIDATE"
                for x in output),
            rejected_fixture_count=sum(
                x["eligibility"] == "REJECTED_BY_RESEARCH_SCREEN"
                for x in output),
            observed_first_source_response_utc=captured.isoformat(),
            observed_source_latest_result_day=latest_date.isoformat(),
            source_age_days_at_original_capture=(captured.date()-latest_date).days,
            fixtures=output,
            only_forward_filter_no_lookahead=True,
            not_a_proven_backtest_uplift=True,
        )
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return _report(
            "INVALID_UNVERIFIED_INPUT_OR_CLOCK",
            safe_failure_reason=str(exc) if type(exc) is ValueError
            and str(exc) in (
                "INVALID_FIXED_CLOCK", "INVALID_SOURCE_RESULT_DATE",
                "INVALID_PREMATCH_VECTOR", "INVALID_ASSESSMENT_CLOCK",
                "INVALID_SOURCE_MATCH_IDENTITY",
                "DUPLICATE_OR_CONFLICTED_MATCH")
            else "RESEARCH_INPUT_REJECTED",
        )


def main(argv=None):
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if Path(args.input).resolve() == Path(args.output).resolve():
        raise ValueError("INPUT_OUTPUT_ALIAS")
    def no_duplicates(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise ValueError("DUPLICATE_PROOF_JSON_KEY")
            result[k] = v
        return result
    data = json.loads(Path(args.input).read_text(encoding="utf-8"),
                      object_pairs_hook=no_duplicates,
                      parse_constant=lambda _: (_ for _ in ()).throw(
                          ValueError("NONFINITE_JSON")))
    report = screen(data)
    target = Path(args.output)
    if target.exists() or target.is_symlink():
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    target.write_text(json.dumps(report, sort_keys=True,
                                 ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "HOLD", "reason": report["reason"],
        "unverified_candidate_count": report.get("unverified_candidate_count", 0),
        "rejected_fixture_count": report.get("rejected_fixture_count", 0),
        "production_recommendations": "DISABLED",
    }, sort_keys=True))
    return 0 if "fixtures" in report else 1


if __name__ == "__main__":
    raise SystemExit(main())
