"""Strict *offline*, per-fixture as-of alignment for A/challenger/market.

This is an original research adapter, not a source-authentication mechanism.
All fixture labels, producer identities and timestamps are caller supplied.
No live odds, scraping, signed forecasts, deployment, EV or wagering.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import math
import re

SCHEMA = "football-king-paired-snapshot-alignment-v1"
MAX_COHORT = 5000
MAX_AGE_MINUTES = 120
MODELS = ("model_a", "challenger")
STREAMS = (*MODELS, "market")
IDENTITY = {"source_namespace", "fixture_id", "league_id",
            "home_team_id", "away_team_id", "kickoff_utc", "as_of_utc"}
RESULT_FIELDS = IDENTITY | {"result_received_utc", "outcome"}
MODEL_FIELDS = IDENTITY | {"produced_utc", "max_input_received_utc",
                           "probabilities"}
MARKET_FIELDS = IDENTITY | {"quote_received_utc", "bookmaker_id",
                            "market_type", "probabilities"}


def _hold(reason, **extra):
    # Every path, including apparently valid cross-checks, is research HOLD.
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "production_recommendations": "DISABLED",
        "positive_ev_verified": False, "model_promoted": False,
        "eligible_for_model_scoring": False,
        "certified_prospective_samples": 0,
        "independent_provenance_verified": False,
        "independent_score_verified": False,
        "trusted_forecast_timestamp_verified": False,
        "trusted_market_quote_verified": False,
        **extra,
    }


def _id(value, *, namespace=False):
    if (type(value) is not str or not 1 <= len(value) <= 128
            or value != value.strip()
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)):
        raise ValueError("INVALID_NATIVE_ID")
    if namespace and not re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", value):
        raise ValueError("INVALID_SOURCE_NAMESPACE")


def _utc(value):
    if type(value) is not str or not 1 <= len(value) <= 64:
        raise ValueError("INVALID_TIMESTAMP")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("INVALID_TIMESTAMP")
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("INVALID_TIMESTAMP") from None


def _probabilities(values):
    if (type(values) is not list or len(values) != 3
            or any(type(x) not in (float, int) or not math.isfinite(x)
                   or not 0 <= x <= 1 for x in values)
            or abs(sum(values) - 1) > 1e-6):
        raise ValueError("INVALID_PROBABILITIES")
    return values


def _identity(row):
    for name in ("source_namespace", "fixture_id", "league_id",
                 "home_team_id", "away_team_id"):
        _id(row[name], namespace=(name == "source_namespace"))
    if row["home_team_id"] == row["away_team_id"]:
        raise ValueError("SELF_MATCH")
    return row["source_namespace"], row["fixture_id"]


def _score(rows, results):
    totals = {
        key: {"accuracy": 0, "brier": 0.0, "log_loss": 0.0}
        for key in STREAMS
    }
    for key, result in results.items():
        y = result["outcome"]
        for name in STREAMS:
            p = rows[name][key]["probabilities"]
            acc = totals[name]
            acc["accuracy"] += int(max(range(3), key=lambda i: p[i]) == y)
            acc["brier"] += sum((prob - int(i == y)) ** 2
                                for i, prob in enumerate(p))
            acc["log_loss"] += -math.log(max(p[y], 1e-15))
    size = len(results)
    return {name: {metric: round(value / size, 8)
                   for metric, value in metrics.items()}
            for name, metrics in totals.items()}


def audit_aligned(payload):
    """Require exact native fixture identity and shared decision cutoff.

    All three observations must be available at the common cutoff. Market
    must also have been received by the time either model was produced, to
    prevent a later quote being passed off as a contemporaneous comparator.
    Even when valid, this can verify ONLY structural, caller-supplied fields.
    """
    if (type(payload) is not dict or
            set(payload) != {"schema", "production_recommendations",
                             "fixtures", "model_a", "challenger", "market"} or
            payload.get("schema") != SCHEMA or
            payload.get("production_recommendations") != "DISABLED"):
        return _hold("INVALID_ALIGNMENT_CONTRACT")
    fixtures = payload["fixtures"]
    if type(fixtures) is not list or not 1 <= len(fixtures) <= MAX_COHORT:
        return _hold("INVALID_COHORT_SIZE")
    try:
        results, kickoffs, cutoffs = {}, {}, {}
        for row in fixtures:
            if type(row) is not dict or set(row) != RESULT_FIELDS:
                raise ValueError("INVALID_RESULT_SCHEMA")
            key = _identity(row)
            if key in results:
                raise ValueError("DUPLICATE_OR_UNKNOWN_FIXTURE")
            kickoff, cutoff = _utc(row["kickoff_utc"]), _utc(row["as_of_utc"])
            if not cutoff < kickoff:
                raise ValueError("NOT_PREMATCH_CUTOFF")
            if _utc(row["result_received_utc"]) < kickoff + timedelta(minutes=90):
                raise ValueError("RESULT_RECORDED_BEFORE_REGULATION_END")
            if type(row["outcome"]) is not int or row["outcome"] not in (0, 1, 2):
                raise ValueError("INVALID_OUTCOME")
            results[key], kickoffs[key], cutoffs[key] = row, kickoff, cutoff

        streams, model_times, quote_times = {}, {}, {}
        for name in STREAMS:
            values = payload[name]
            if type(values) is not list or len(values) != len(results):
                raise ValueError("INCOMPLETE_PAIRED_COHORT")
            index = {}
            for row in values:
                fields = MARKET_FIELDS if name == "market" else MODEL_FIELDS
                if type(row) is not dict or set(row) != fields:
                    raise ValueError("INVALID_PAIRED_STREAM_SCHEMA")
                key = _identity(row)
                if key not in results or key in index:
                    raise ValueError("DUPLICATE_OR_UNKNOWN_FIXTURE")
                expected = results[key]
                for field in ("league_id", "home_team_id", "away_team_id"):
                    if row[field] != expected[field]:
                        raise ValueError("FIXTURE_IDENTITY_MISMATCH")
                if _utc(row["kickoff_utc"]) != kickoffs[key]:
                    raise ValueError("KICKOFF_MISMATCH")
                cutoff = cutoffs[key]
                if _utc(row["as_of_utc"]) != cutoff:
                    raise ValueError("CUTOFF_MISMATCH")
                _probabilities(row["probabilities"])
                if name == "market":
                    _id(row["bookmaker_id"])
                    if row["market_type"] != "1X2":
                        raise ValueError("UNSUPPORTED_MARKET")
                    quote = _utc(row["quote_received_utc"])
                    if quote > cutoff:
                        raise ValueError("MARKET_TIME_INVALID")
                    if cutoff - quote > timedelta(minutes=MAX_AGE_MINUTES):
                        raise ValueError("STALE_MARKET_SNAPSHOT")
                    quote_times[key] = quote
                else:
                    produced = _utc(row["produced_utc"])
                    last_input = _utc(row["max_input_received_utc"])
                    if not last_input <= produced <= cutoff:
                        raise ValueError("MODEL_SNAPSHOT_OR_INPUT_LOOKAHEAD")
                    if cutoff - produced > timedelta(minutes=MAX_AGE_MINUTES):
                        raise ValueError("STALE_MODEL_SNAPSHOT")
                    model_times[(name, key)] = produced
                index[key] = row
            if set(index) != set(results):
                raise ValueError("INCOMPLETE_PAIRED_COHORT")
            streams[name] = index

        for key in results:
            earliest_model = min(model_times[(name, key)] for name in MODELS)
            if quote_times[key] > earliest_model:
                raise ValueError("MARKET_AFTER_MODEL_SNAPSHOT")

        diagnostics = _score(streams, results)
        return _hold(
            "ALIGNED_TRANSCRIPTIONS_ONLY_EXTERNAL_ATTESTATION_MISSING",
            paired_fixture_count=len(results),
            unverified_diagnostic_metrics=diagnostics,
            per_fixture_native_identity_checked=True,
            shared_cutoff_consistent_by_claim=True,
            quote_precedes_both_model_snapshots_by_claim=True,
            max_snapshot_age_minutes=MAX_AGE_MINUTES,
            note=("All source and snapshot timestamps are untrusted inputs; "
                  "no attested OOS, verified market odds, accuracy lift or EV."),
        )
    except (ValueError, KeyError, TypeError, OverflowError, AttributeError) as exc:
        return _hold(str(exc) if len(str(exc)) < 120 else
                     "INVALID_OR_UNTRUSTED_ALIGNED_DATA")


def _unique_pairs(pairs):
    result = {}
    for key, val in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = val
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline paired snapshot research gate")
    parser.add_argument("--input", required=True)
    args = parser.parse_args(argv)
    try:
        with open(args.input, "r", encoding="utf-8") as handle:
            data = json.load(
                handle, object_pairs_hook=_unique_pairs,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))
        report = audit_aligned(data)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        report = _hold(str(exc) if len(str(exc)) < 120 else "INVALID_JSON")
    print(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False))
    return 0 if "unverified_diagnostic_metrics" in report else 1


if __name__ == "__main__":
    raise SystemExit(main())
