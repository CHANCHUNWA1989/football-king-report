"""Fail-closed live recommendation safety gate.

This gate NEVER turns a pre-match forecast into an in-play betting tip.
Two matching provider labels are *not* authenticated independent source
evidence. This module has no trusted producer receipts or source identity
verification, so it can expose a clearly unverified matching candidate but
NEVER label a live/final score verified or enable betting. Conflicts force HOLD.
"""
from datetime import datetime, timezone, timedelta

MAX_SCORE_AGE_SECONDS = 90
LIVE_STATES = {"LIVE", "FIRST_HALF", "HALF_TIME", "SECOND_HALF", "EXTRA_TIME"}
FINISHED_STATES = {"FINISHED", "FULL_TIME"}

def _dt(value):
    if not isinstance(value, str):
        raise ValueError("MISSING_TIME")
    t=datetime.fromisoformat(value.replace("Z","+00:00"))
    if t.tzinfo is None:
        raise ValueError("NAIVE_TIME")
    return t.astimezone(timezone.utc)

def evaluate(kickoff_utc, observations, *, now=None):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    kickoff=_dt(kickoff_utc)
    result={
        "schema":"football-king-live-recommendation-guard-v1",
        "status":"HOLD", "production_recommendations":"DISABLED",
        "betting_recommendation_allowed":False,
        "in_play_betting_recommendation_allowed":False,
        "pre_match_probabilities_reusable_in_play":False,
        "verified_live_score":None,
        "unverified_score_candidate":None,
        "independent_source_authenticated":False,
        "reason":"MISSING_INDEPENDENT_SCORE_CONFIRMATION",
        "checked_utc":now.isoformat(),
    }
    if now < kickoff:
        return {**result,"reason":"PREGAME_REQUIRES_SEPARATE_ODDS_AND_CALIBRATION_GATES"}
    if not isinstance(observations,list) or len(observations)<2:
        return result
    clean=[]
    for o in observations:
        if not isinstance(o,dict):
            continue
        try:
            provider=o["provider"]
            if (type(provider) is not str or not provider.strip()
                    or provider != provider.strip() or len(provider) > 128):
                continue
            state=o["state"]
            if state not in LIVE_STATES|FINISHED_STATES:
                continue
            home,away=o["home_goals"],o["away_goals"]
            if type(home) is not int or type(away) is not int or min(home,away)<0 or max(home,away)>30:
                continue
            stamp=_dt(o["observed_utc"])
            if not timedelta(0)<=now-stamp<=timedelta(seconds=MAX_SCORE_AGE_SECONDS):
                continue
            if stamp<kickoff:
                continue
            clean.append((provider,state,home,away))
        except (KeyError,ValueError,TypeError,OverflowError):
            continue
    if len({r[0] for r in clean})<2:
        return {**result,"reason":"INSUFFICIENT_FRESH_INDEPENDENT_PROVIDERS"}
    by_provider={}
    for provider,state,home,away in clean:
        if provider in by_provider and by_provider[provider]!=(state,home,away):
            return {**result,"reason":"CONFLICTING_SCORE_OBSERVATIONS"}
        by_provider[provider]=(state,home,away)
    if len(set(by_provider.values()))!=1:
        return {**result,"reason":"CONFLICTING_SCORE_OBSERVATIONS"}
    state,home,away=next(iter(by_provider.values()))
    if state in FINISHED_STATES and now < kickoff + timedelta(minutes=90):
        return {**result, "reason":"IMPOSSIBLY_EARLY_FINAL"}
    # Provider names and caller-owned truth flags can be forged. There is no
    # authenticated native fixture binding or original publisher receipt here.
    # Preserve an explicitly unverified diagnostic, never a certified score.
    return {
        **result,
        "reason":"MATCHED_UNAUTHENTICATED_PROVIDER_LABELS",
        "unverified_score_candidate":{
            "home":home, "away":away, "state":state,
            "provider_label_count":len(by_provider),
            "not_valid_for_settlement_or_model_scoring":True,
        },
    }
