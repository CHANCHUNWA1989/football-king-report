"""Conditional live DHE scenarios, never a verified real-time forecast.

No networking, quote intake, xG estimation, trading or release permission.
The constant remaining-rate approximation freezes the observed red-card and
score state; no prediction of future dismissals or stoppage-time duration.
"""
import math
from datetime import timedelta
from asian_handicap_research import quarter_units, _poisson
from deep_handicap_joint_score import _half, _project_score, _total_units
from live_score_identity_guard import check, parse_utc

SCHEMA = "football-king-dhe-live-state-v1"
RED_PROFILES = ((.60,1.10),(.75,1.15),(.90,1.25))
PACE_PROFILES = (.65,.85,1.0)
MAX_AGE = timedelta(seconds=120)


def _remaining_pmf(home,away,h,a,minute,hr,ar,side,profile,pace):
    """Red-card multipliers are hypothetical per-card effects, not fitted."""
    own,opponent=profile
    remaining=(90-minute)/90
    # Each side can lose players. Both effects may apply simultaneously.
    rate_h=home*remaining*own**hr*opponent**ar
    rate_a=away*remaining*own**ar*opponent**hr
    if side=="HOME" and h-a>=2:
        rate_h*=pace
    if side=="AWAY" and a-h>=2:
        rate_a*=pace
    score={(h+i,a+j):p*q for i,p in enumerate(_half(rate_h))
           for j,q in enumerate(_half(rate_a))}
    return score,rate_h,rate_a


def analyze(fixture,observations,*,as_of_utc,home_rate,away_rate,side,handicap,total_line):
    out={"schema":SCHEMA,"status":"HOLD","production_recommendations":"DISABLED",
         "research_only":True,"qualifies_for_betting":False,
         "positive_expected_value_verified":False,"source_authenticated":False,
         "red_card_event_authenticated":False,"actual_kickoff_authenticated":False,
         "live_xg_verified":False,"calibrated":False,"scenarios":[],
         "reason":"UNVERIFIED_LIVE_INPUT"}
    try:
        _poisson(home_rate)
        _poisson(away_rate)
        ah,tu=quarter_units(handicap),_total_units(total_line)
        if ah>-6 or side not in ("HOME","AWAY"):
            raise ValueError("INVALID_DEEP_LINE")
        now=parse_utc(as_of_utc)
        gate=check(fixture,observations,as_of_utc)
        if gate["status"]!="RESEARCH_ONLY":
            raise ValueError("LIVE_IDENTITY_GATE_REJECTED")
        phase=gate["match_status"]
        if phase not in ("FIRST_HALF","HALF_TIME","SECOND_HALF"):
            raise ValueError("NOT_SUPPORTED_LIVE_PHASE")
        states=set()
        ko=parse_utc(fixture["kickoff_utc"])
        for obs in observations:
            captured=parse_utc(obs["captured_utc"])
            updated=parse_utc(obs["source_updated_utc"])
            if not timedelta(0)<=now-updated<=MAX_AGE or not timedelta(0)<=now-captured<=MAX_AGE:
                raise ValueError("STALE_LIVE_STATE")
            if updated<ko:
                raise ValueError("PREKICKOFF_LIVE_UPDATE")
            m,hr,ar=(obs.get("regulation_minute_elapsed"),obs.get("home_red_cards"),
                     obs.get("away_red_cards"))
            if type(m) is not int or any(type(x) is not int or not 0<=x<=2 for x in (hr,ar)):
                raise ValueError("MISSING_OR_INVALID_CLOCK_CARD_COUNTS")
            if not ((phase=="FIRST_HALF" and 0<=m<45)
                    or (phase=="HALF_TIME" and m==45)
                    or (phase=="SECOND_HALF" and 45<=m<90)):
                raise ValueError("CLOCK_PHASE_CONFLICT_OR_STOPPAGE_UNSUPPORTED")
            # Recorded schedule is not actual kickoff. This is only a broad
            # consistency screen; second-half clock excludes halftime.
            wall=(updated-ko).total_seconds()/60
            minimum=m+(10 if phase=="SECOND_HALF" else 0)
            if not minimum-3<=wall<=minimum+35:
                raise ValueError("IMPLAUSIBLE_RECORDED_CLOCK")
            states.add((m,hr,ar))
        if len(states)!=1:
            raise ValueError("CROSS_SOURCE_CLOCK_OR_CARD_CONFLICT")
        minute,hr,ar=states.pop()
        h,a=gate["score_home"],gate["score_away"]
        for profile in RED_PROFILES:
            for pace in PACE_PROFILES:
                score,rh,ra=_remaining_pmf(home_rate,away_rate,h,a,minute,hr,ar,side,profile,pace)
                if abs(math.fsum(score.values())-1)>1e-9:
                    raise ValueError("INVALID_SCORE_MASS")
                v=_project_score(score,side,ah,tu,pace)
                v.update(schema=SCHEMA,score_support_max_per_team=max(h,a)+24,
                         model_assumption="FROZEN_CURRENT_STATE_REMAINING_REGULATION_ONLY",
                         remaining_home_goal_rate=rh,remaining_away_goal_rate=ra,
                         red_profile=list(profile))
                out["scenarios"].append(v)
        p=[v["handicap"]["FULL_WIN"] for v in out["scenarios"]]
        out.update(reason="CONCORDANT_SOURCE_CLAIMS_SYNTHETIC_SCENARIOS_ONLY",
                   scenario_count=len(p),full_win_envelope={"min":min(p),"max":max(p)},
                   regulation_minute_elapsed=minute,score=[h,a],red_cards=[hr,ar],
                   match_status=phase,stoppage_time_modelled=False,
                   future_red_cards_modelled=False,goal_rates_are_assumptions=True)
    except (ValueError,TypeError,KeyError,OverflowError,AttributeError) as exc:
        out["scenarios"]=[]
        out["reason"]=str(exc) if str(exc) in (
            "INVALID_DEEP_LINE","LIVE_IDENTITY_GATE_REJECTED","NOT_SUPPORTED_LIVE_PHASE",
            "STALE_LIVE_STATE","PREKICKOFF_LIVE_UPDATE","MISSING_OR_INVALID_CLOCK_CARD_COUNTS",
            "CLOCK_PHASE_CONFLICT_OR_STOPPAGE_UNSUPPORTED","IMPLAUSIBLE_RECORDED_CLOCK",
            "CROSS_SOURCE_CLOCK_OR_CARD_CONFLICT","INVALID_SCORE_MASS") else "INVALID_LIVE_INPUT"
    return out
