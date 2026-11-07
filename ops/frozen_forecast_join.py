"""Research-only point-in-time join of archived forecasts and odds.

No invented forecasts, outcomes, or bookmaker timestamps; no EV certification.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

PRODUCTION_RECOMMENDATIONS = "DISABLED"
POSITIVE_EV_VERIFIED = False

def _time(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be ISO8601")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return dt.astimezone(timezone.utc)

def _decimal(value):
    if isinstance(value, bool):
        raise ValueError("boolean number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid number") from exc
    if not result.is_finite():
        raise ValueError("nonfinite number")
    return result

def join_frozen_forecasts(quotes, forecasts, results, *, max_bookmaker_age_minutes=30):
    """Join by exact provider namespace and native ID, never by names or bare ID.

    All inputs require event_source (the ID namespace) and native event_id.
    Cross-source aliases are unsupported pending independent mapping verification;
    caller-supplied mapping claims cannot authorize an automatic match.
    Forecasts must contain created_at, model_version, model_artifact_sha256,
    training_data_cutoff_at, score_probabilities.
    Results must contain event_id, home_goals, away_goals, or be None for a
    pre-match join without outcomes. Never insert placeholder final scores.
    Returned rows are structurally checked, NOT independently authenticated.
    """
    if (isinstance(max_bookmaker_age_minutes, bool)
        or not isinstance(max_bookmaker_age_minutes, (int, float))
        or not 0 < max_bookmaker_age_minutes <= 1440):
        raise ValueError("invalid maximum age")
    if not isinstance(quotes, (list, tuple)) or not quotes:
        raise ValueError("quotes required")
    if not isinstance(forecasts, (list, tuple)) or (results is not None and not isinstance(results, (list, tuple))):
        raise ValueError("forecast and result collections required")
    def identity(row):
        if not isinstance(row, dict):
            raise ValueError("invalid event identity")
        key = (row.get("event_source"), row.get("event_id"))
        if any(not isinstance(value, str) or not value.strip()
               or value != value.strip() for value in key):
            raise ValueError("explicit event source and native event id required")
        return key
    def index(rows):
        out = {}
        for row in rows:
            key = identity(row)
            if key in out:
                raise ValueError("duplicate source event id")
            out[key] = row
        return out
    fidx, ridx = index(forecasts), index(results) if results is not None else None
    output = []
    seen = set()
    for quote in quotes:
        if not isinstance(quote, dict):
            raise ValueError("quote must be mapping")
        if quote.get("bookmaker_timestamp_checked") is not True:
            raise ValueError("quote freshness gate not passed")
        if quote.get("production_recommendation_allowed") is not False:
            raise ValueError("quote must be research-only")
        captured_for_freshness = _time(quote["captured_at"])
        for field in ("bookmaker_last_update", "market_last_update"):
            updated = _time(quote.get(field))
            if updated > captured_for_freshness:
                raise ValueError("source update after quote snapshot")
            if (captured_for_freshness - updated).total_seconds() > max_bookmaker_age_minutes * 60:
                raise ValueError("stale source update")
        eid = identity(quote)
        # Compare numeric lines and UTC instants, retaining raw source fields.
        key = (eid, quote["bookmaker"], quote["market"], quote["side"], _decimal(quote["line"]), captured_for_freshness)
        if key in seen:
            raise ValueError("duplicate quote")
        seen.add(key)
        if eid not in fidx or (ridx is not None and eid not in ridx):
            raise ValueError("missing same-source forecast or result; cross-source mapping not verified")
        forecast = fidx[eid]
        captured, kickoff = _time(quote["captured_at"]), _time(quote["kickoff_at"])
        created = _time(forecast["created_at"])
        cutoff = _time(forecast["training_data_cutoff_at"])
        if not cutoff <= created <= captured < kickoff:
            raise ValueError("lookahead or post-kickoff data")
        sha = forecast.get("model_artifact_sha256")
        if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdefABCDEF" for c in sha):
            raise ValueError("model artifact SHA256 required")
        if not isinstance(forecast.get("model_version"), str) or not forecast["model_version"].strip():
            raise ValueError("model version required")
        probabilities = forecast.get("score_probabilities")
        if not isinstance(probabilities, dict) or not probabilities:
            raise ValueError("missing score probabilities")
        total = Decimal(0)
        for score, prob in probabilities.items():
            if not isinstance(score, str) or len(score.split("-")) != 2 or any(not s.isdecimal() for s in score.split("-")):
                raise ValueError("invalid score key")
            p = _decimal(prob)
            if p < 0 or p > 1:
                raise ValueError("invalid probability")
            total += p
        if abs(total - 1) > Decimal("0.000001"):
            raise ValueError("probabilities do not sum to one")
        if quote["market"] not in ("total", "handicap"):
            raise ValueError("unsupported market")
        if quote["side"] not in (("over", "under") if quote["market"] == "total" else ("home", "away")):
            raise ValueError("unsupported selection")
        odds = _decimal(quote["odds"])
        if odds <= 1:
            raise ValueError("invalid decimal odds")
        line = _decimal(quote["line"])
        if line * 4 != (line * 4).to_integral_value():
            raise ValueError("invalid quarter-goal line")
        row = {**quote, "forecast_created_at": forecast["created_at"],
                       "model_version": forecast["model_version"],
                       "model_artifact_sha256": sha,
                       "training_data_cutoff_at": forecast["training_data_cutoff_at"],
                       "score_probabilities": dict(probabilities),
                       "source_authenticity_verified": False,
                       "out_of_sample_verified": False,
                       "positive_ev_verified": False,
                       "production_recommendation_allowed": False}
        if ridx is None:
            if any(field in quote for field in ("home_goals", "away_goals", "outcome", "result")):
                raise ValueError("pre-match quote must not contain results")
            row["outcome_status"] = "NOT_YET_SETTLED"
        else:
            for name in ("home_goals", "away_goals"):
                n = _decimal(ridx[eid][name])
                if n < 0 or n != n.to_integral_value():
                    raise ValueError("invalid final score")
                row[name] = int(n)
        output.append(row)
    return output


def join_historical_envelope(envelope, forecasts, results, *, max_bookmaker_age_minutes=30):
    """Preferred entry point: run timestamp gate on raw provider envelope first.

    Avoid trusting caller-supplied bookmaker_timestamp_checked flags in quote rows.
    Does not authenticate source or independently verify forecast provenance.
    """
    from ops.bookmaker_timestamp_gate import extract_verified_time_quotes
    quotes = extract_verified_time_quotes(
        envelope, max_bookmaker_age_minutes=max_bookmaker_age_minutes
    )
    return join_frozen_forecasts(quotes, forecasts, results, max_bookmaker_age_minutes=max_bookmaker_age_minutes)
