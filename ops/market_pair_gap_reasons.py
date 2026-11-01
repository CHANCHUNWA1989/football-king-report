"""Read-only, per-fixture explanation of strict model/market pairing failures.

This only audits snapshots already available to the six-league shadow pipeline.
No live queries, synthetic prices, odds, EV, settlement or betting admission.
It must not change the real matcher or reclassify failed forecasts as paired.
"""
import argparse
from collections import Counter
from datetime import timezone
import json
from pathlib import Path

from market_pair import iso, pair, vector
from team_identity import team_id

MAX_DISPLAY = 100
MATCH_WINDOW_SECONDS = 45 * 60
MAX_MARKET_AGE_SECONDS = 8 * 3600
MAX_SNAPSHOT_LAG_SECONDS = 750 * 60


def _key(row):
    league = row.get("league")
    h = team_id(league, row.get("home"))
    a = team_id(league, row.get("away"))
    if not isinstance(league, str) or not h or not a or h == a:
        raise ValueError("BAD_TEAMS")
    return league, h, a


def _clock(row, field):
    try:
        return iso(row[field])
    except (TypeError, KeyError, ValueError, OverflowError, AttributeError):
        return None


def _reason(forecast, quotes, snapshot_at, forecast_at):
    try:
        if (not isinstance(forecast, dict)
                or forecast.get("production_recommendations") != "DISABLED"
                or vector(forecast) is None):
            return "INVALID_FORECAST_OR_TIME"
        identity = _key(forecast)
        pred = _clock(forecast, "prediction_utc")
        kickoff = _clock(forecast, "kickoff_utc")
        if (pred is None or kickoff is None or
                abs((pred - forecast_at).total_seconds()) > 120 or
                snapshot_at > pred or
                (kickoff - pred).total_seconds() <= 600):
            return "INVALID_FORECAST_OR_TIME"
        same = [q for q in quotes if isinstance(q, dict)
                and _valid_team_key(q, identity)]
        if not same:
            return "NO_SAME_LEAGUE_TEAM_MARKET_EVENT"
        usable = [q for q in same
                  if vector(q) is not None and
                  isinstance(q.get("source_event_id"), str)
                  and q["source_event_id"].strip()]
        if not usable:
            return "NO_USABLE_MARKET_PROBABILITY"
        dated = [(q, _clock(q, "kickoff_utc"),
                  _clock(q, "market_last_update_utc")) for q in usable]
        dated = [(q, k, u) for q, k, u in dated if k is not None and u is not None]
        if not dated:
            return "INVALID_MARKET_KICKOFF_OR_UPDATE"
        timely = [(q, k, u) for q, k, u in dated
                  if 0 <= (snapshot_at-u).total_seconds() <= MAX_MARKET_AGE_SECONDS
                  and k > snapshot_at]
        if not timely:
            return "QUOTE_NOT_VALID_AT_MARKET_CAPTURE"
        kickoff_match = [(q, k, u) for q, k, u in timely
                         if abs((k - kickoff).total_seconds()) <= MATCH_WINDOW_SECONDS]
        if not kickoff_match:
            return "MARKET_KICKOFF_MORE_THAN_45M_AWAY"
        earlier = [(q, k, u) for q, k, u in kickoff_match if u <= pred]
        if not earlier:
            return "QUOTE_AFTER_MODEL_PREDICTION"
        if len(earlier) > 1:
            return "AMBIGUOUS_MARKET_MATCH"
        return "PAIR_REJECTED_NEEDS_REVIEW"
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return "INVALID_FORECAST_OR_TIME"


def _valid_team_key(row, key):
    try:
        return _key(row) == key
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def diagnose(shadow, market, paired):
    """Explain currently unpaired forecasts; all output remains unverified."""
    out = {
        "schema": "football-king-market-pair-gap-reasons-v1",
        "status": "HOLD",
        "reason": "INVALID_OR_UNSAFE_INPUT",
        "forecast_total": 0, "paired_forecasts": 0,
        "unpaired_forecasts": 0,
        "fixtures": [], "reasons": {},
        "not_displayed_due_to_bound": 0,
        "no_model_probabilities_or_original_market_quotes_exported": True,
        "eligible_for_model_scoring": False,
        "verified_ev": False, "production_recommendations": "DISABLED",
    }
    if (not all(isinstance(x, dict) for x in (shadow, market, paired))
            or shadow.get("status") != "SHADOW_ONLY"
            or market.get("status") != "RESEARCH_ONLY"
            or paired.get("status") not in ("HOLD", "RESEARCH_ONLY")
            or any(x.get("production_recommendations") != "DISABLED"
                   for x in (shadow, market, paired))
            or not isinstance(shadow.get("predictions"), list)
            or not isinstance(market.get("events"), list)
            or not isinstance(paired.get("comparisons"), list)
            or type(paired.get("matched_count")) is not int
            or paired["matched_count"] != len(paired["comparisons"])):
        return out
    forecast_at = _clock(shadow, "as_of_utc")
    market_at = _clock(market, "as_of_utc")
    if forecast_at is None or market_at is None:
        return out
    lag = (forecast_at-market_at).total_seconds()
    if not 0 <= lag <= MAX_SNAPSHOT_LAG_SECONDS:
        return out

    # Pairing is existing strict matcher output. Only count a comparison when
    # the same league/teams/UTC kickoff/model timestamp is represented.
    matched = Counter()
    try:
        for c in paired["comparisons"]:
            if (not isinstance(c, dict) or
                    c.get("production_recommendations") != "DISABLED" or
                    c.get("available_for_betting") is not False):
                return out
            key = (*_key(c), _clock(c, "kickoff_utc"),
                   _clock(c, "prediction_utc"))
            if key[-1] is None or key[-2] is None:
                return out
            matched[key] += 1
    except (KeyError, TypeError, ValueError, AttributeError):
        return out

    rows = []
    reasons = Counter()
    paired_forecasts = 0
    for f in shadow["predictions"]:
        try:
            key = (*_key(f), _clock(f, "kickoff_utc"), _clock(f, "prediction_utc"))
            if key[-1] is not None and key[-2] is not None and matched[key]:
                matched[key] -= 1
                paired_forecasts += 1
                continue
        except (KeyError, TypeError, ValueError, AttributeError):
            pass
        reason = _reason(f, market["events"], market_at, forecast_at)
        reasons[reason] += 1
        if len(rows) < MAX_DISPLAY:
            # The three fields below are fixture metadata, not market proof.
            rows.append({
                "league": f.get("league") if isinstance(f, dict) else None,
                "home": f.get("home") if isinstance(f, dict) else None,
                "away": f.get("away") if isinstance(f, dict) else None,
                "kickoff_utc": f.get("kickoff_utc") if isinstance(f, dict) else None,
                "reason": reason,
                "value_bet_verified": False,
                "production_recommendations": "DISABLED",
            })
    if sum(matched.values()):
        return out  # inconsistent comparison set is not evidence
    out.update({
        "status": "RESEARCH_ONLY",
        "reason": "STRICT_PAIRING_GAP_EXPLANATION_NOT_BETTING_ADVICE",
        "forecast_total": len(shadow["predictions"]),
        "paired_forecasts": paired_forecasts,
        "unpaired_forecasts": sum(reasons.values()),
        "fixtures": rows,
        "reasons": dict(sorted(reasons.items())),
        "not_displayed_due_to_bound": max(0, sum(reasons.values())-len(rows)),
        "shadow_as_of_utc": forecast_at.isoformat(),
        "market_as_of_utc": market_at.isoformat(),
    })
    return out


def publish(site, market_file):
    site = Path(site)
    shadow = json.loads((site/"shadow.json").read_text(encoding="utf-8"))
    market = json.loads(Path(market_file).read_text(encoding="utf-8"))
    paired = pair(shadow, market)
    report = diagnose(shadow, market, paired)
    (site/"market_pair_gap_reasons.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--site", default="app/site")
    p.add_argument("--market", default="market/latest.json")
    a = p.parse_args()
    report = publish(a.site, a.market)
    print(json.dumps({
        "status": report["status"],
        "paired_forecasts": report["paired_forecasts"],
        "unpaired_forecasts": report["unpaired_forecasts"],
        "reasons": report["reasons"],
        "production_recommendations": "DISABLED",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
