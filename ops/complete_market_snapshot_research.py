"""Research-only complete 1X2 market price snapshot normalization.

Do not infer quarter-line outcome probabilities from two opposing prices.
Declared snapshot time, bookmaker identity and prices are not authenticated.
No source fetch, staking, execution or verified EV.
"""
from math import fsum, isfinite
from datetime import timedelta
from ops.first_case_payload_binding import _time, _name

OUTCOMES=("HOME","DRAW","AWAY")
KEYS={"fixture_id","provider","provider_event_id","bookmaker","market",
      "observed_utc","captured_utc","kickoff_utc","prices","production_recommendations"}


def audit(snapshot,forecast_utc):
    out={"status":"HOLD","production_recommendations":"DISABLED",
         "positive_ev_verified":False,"executable_prices_authenticated":False,
         "source_time_authenticated":False,"certified_prospective_samples":0}
    try:
        if type(snapshot) is not dict or set(snapshot)!=KEYS or snapshot["market"]!="h2h" or snapshot["production_recommendations"]!="DISABLED":
            raise ValueError("COMPLETE_1X2_SNAPSHOT_REQUIRED")
        for k in ("fixture_id","provider","provider_event_id","bookmaker"):
            _name(snapshot[k])
        o,c,k,f=(_time(v) for v in (snapshot["observed_utc"],snapshot["captured_utc"],snapshot["kickoff_utc"],forecast_utc))
        if not o<=c<=f<k or f-o>timedelta(seconds=120):
            raise ValueError("STALE_OR_FUTURE_QUOTE")
        prices=snapshot["prices"]
        if type(prices) is not dict or set(prices)!=set(OUTCOMES) or any(
            type(v) not in (int,float) or not isfinite(v) or not 1.01<=v<=100
            for v in prices.values()):
            raise ValueError("INVALID_COMPLETE_PRICE_VECTOR")
        q={k:1/prices[k] for k in OUTCOMES}
        mass=fsum(q.values())
        if not 1<=mass<=1.30:
            raise ValueError("OUTSIDE_PILOT_OVERROUND_RANGE")
        p={k:q[k]/mass for k in OUTCOMES}
        return {**out,"reason":"DECLARED_SNAPSHOT_MATH_ONLY",
                "declared_quote_age_seconds":(f-o).total_seconds(),
                "overround":mass-1,
                "proportional_no_vig_probabilities":p,
                "proportional_fair_decimal_odds":{k:1/p[k] for k in OUTCOMES},
                "normalization_method":"PROPORTIONAL_NOT_TRUE_PROBABILITY",
                "same_bookmaker_snapshot_claim":True}
    except (TypeError,ValueError,KeyError,AttributeError,OverflowError):
        return {**out,"reason":"INVALID_OR_UNSUPPORTED_SNAPSHOT"}
