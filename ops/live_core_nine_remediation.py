"""Integrated multi-cut LIVE-CORE research admission and sensitivity audit.

Captured bytes only. A batch is a caller-supplied history, not a durable
authenticated feed. Never overwrite an earlier forecast or certify EV.
"""
import math
from live_core_provider_evidence import normalize
from live_core_sportmonks_capture import parse,dual_run
from live_core_real_observations import digest
from live_core_event_revision import audit
from live_snapshot_adapter import hold
from inplay_state_challenger_vnext import remaining_matrix,FIXED_SCORE_COEFFICIENT
from score_distribution_vnext import one_x_two,market_distribution

CUT_KEYS={"primary_raw","secondary_raw","primary_clock","secondary_clock","now"}
CONTEXT_KEYS={"fixture_id","minute","observed","source_url","keeper_psxg_faced",
              "keeper_goals_conceded","competition_format","aggregate_score",
              "tie_rule","announced_added_minutes"}
RED_GRID=(.1,.2,.4)
STOPPAGE_GRID=(0,5,10)


def finite_pair(x,limit):
    return type(x) is list and len(x)==2 and all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=limit for v in x)


def audit_context(context,state,now):
    """Context claims are diagnostics only; missing is not zero."""
    if context is None:
        return {"keeper_available":False,"knockout_available":False,"added_time_available":False}
    from urllib.parse import urlsplit
    if type(context) is not dict or set(context)!=CONTEXT_KEYS:
        raise ValueError("CONTEXT_SCHEMA")
    c=context
    u=urlsplit(c["source_url"])
    if u.scheme!="https" or not u.hostname or u.username or u.password or u.query or u.fragment:
        raise ValueError("CONTEXT_URL")
    if (c["fixture_id"]!=state["fixture_id"] or type(c["minute"]) is not int or c["minute"]!=state["minute"]
            or type(c["observed"]) is not int or not 0<=now-c["observed"]<=30
            or abs(c["observed"]-state["observed"])>30):
        raise ValueError("CONTEXT_CLOCK")
    ps,goals=c["keeper_psxg_faced"],c["keeper_goals_conceded"]
    if (ps is None)!=(goals is None):
        raise ValueError("INCOMPLETE_KEEPER")
    if ps is not None and (not finite_pair(ps,30) or not finite_pair(goals,10)
            or any(type(v) is not int for v in goals)):
        raise ValueError("KEEPER_RANGE")
    fmt=c["competition_format"]
    if fmt not in (None,"LEAGUE","KNOCKOUT_SINGLE","KNOCKOUT_TWO_LEG"):
        raise ValueError("COMPETITION_FORMAT")
    ag,rule=c["aggregate_score"],c["tie_rule"]
    if fmt=="KNOCKOUT_TWO_LEG":
        if not finite_pair(ag,30) or any(type(v) is not int for v in ag) or rule not in ("EXTRA_TIME","RANK_ADVANTAGE","AWAY_GOALS","PENALTIES"):
            raise ValueError("KNOCKOUT_CONTEXT")
    elif ag is not None or rule is not None:
        raise ValueError("UNEXPECTED_TIE_CONTEXT")
    added=c["announced_added_minutes"]
    if added is not None and (type(added) is not int or not 0<=added<=30 or state["minute"]<85):
        raise ValueError("ADDED_TIME_CLAIM")
    return {"keeper_available":ps is not None,"knockout_available":fmt in ("KNOCKOUT_SINGLE","KNOCKOUT_TWO_LEG"),
            "added_time_available":added is not None,"keeper_claim_used":False,
            "knockout_claim_used":False,"added_time_claim_used":False,"context_authenticated":False}


def sensitivity(state,prematch,markets):
    """Untrained assumptions only. Unified grid per scenario, not a forecast."""
    scoregap=max(-4,min(4,state["home"]-state["away"]))
    redgap=state["red_away"]-state["red_home"]
    out=[]
    for red in RED_GRID:
        for added in STOPPAGE_GRID:
            remain=(90-state["minute"]+added)/90
            h=prematch["expected_home_goals"]*remain*math.exp(-FIXED_SCORE_COEFFICIENT*scoregap+red*redgap)
            a=prematch["expected_away_goals"]*remain*math.exp(FIXED_SCORE_COEFFICIENT*scoregap-red*redgap)
            grid=remaining_matrix(h,a,state["home"],state["away"])
            out.append({"red_coefficient_assumption":red,"extra_minutes_assumption":added,
                        "remaining_expected_goals":[h,a],"probabilities_1x2":one_x_two(grid),
                        "market_distributions":[market_distribution(grid,**m) for m in markets]})
    return out


def review(cuts,*,primary_mapping,secondary_mapping,prematch,markets,quotes=None,context=None):
    """Validate both captured sources at every cut before any scenario output."""
    try:
        if type(cuts) is not list or not 2<=len(cuts)<=48:
            raise ValueError("REQUIRE_MULTI_CUT_HISTORY")
        prior=None;prev_xg=None;prev_now=None
        seen_pairs=set();seen_primary=set();seen_secondary=set()
        prior_clocks=None
        ledger=[]
        for i,c in enumerate(cuts):
            if type(c) is not dict or set(c)!=CUT_KEYS:
                raise ValueError("CUT_SCHEMA")
            now=c["now"]
            if type(now) is not int or (prev_now is not None and now<=prev_now):
                raise ValueError("CUT_DECISION_ORDER")
            a,xg=normalize(c["primary_raw"],primary_mapping,now=now,**c["primary_clock"])
            b=parse(c["secondary_raw"],secondary_mapping,now=now,**c["secondary_clock"])
            pair=(a["payload_sha256"],b["payload_sha256"])
            if pair in seen_pairs:
                return hold("REPEATED_BOTH_RAW_CAPTURES")
            # A new caller timestamp cannot refresh identical provider bytes.
            # Conservative research rule: both sources must advance; legitimate
            # unchanged snapshots can be held, never counted as fresh evidence.
            if pair[0] in seen_primary or pair[1] in seen_secondary:
                return hold("REPEATED_SINGLE_RAW_CAPTURE")
            clocks=tuple(tuple(c[k][f] for f in ("observed_claim","captured","received"))
                         for k in ("primary_clock","secondary_clock"))
            if prior_clocks is not None and any(
                    new<=old for current,previous in zip(clocks,prior_clocks)
                    for new,old in zip(current,previous)):
                return hold("PROVIDER_CLOCK_NOT_ADVANCING")
            if prior is not None:
                rev=audit(prior,a,b,now)
                if rev.get("reason")!="MONOTONIC_TRANSITION_CLAIM":
                    return hold("STATE_REVISION_QUARANTINE")
            if prev_xg is not None:
                if xg is None:
                    return hold("XG_DISAPPEARED")
                if xg["source_url"]!=prev_xg["source_url"] or xg["observed"]<=prev_xg["observed"]:
                    return hold("XG_SOURCE_OR_CLOCK_CHANGED")
                if any(xg[k]+1e-9<prev_xg[k] for k in ("home","away")):
                    return hold("XG_REVISION_QUARANTINE")
            out=dual_run(c["primary_raw"],primary_mapping,c["secondary_raw"],secondary_mapping,
                         primary_clock=c["primary_clock"],secondary_clock=c["secondary_clock"],now=now,
                         prematch=prematch,markets=markets,quotes=quotes if i==len(cuts)-1 else None)
            if out.get("research_status")!="RESEARCH_ONLY":
                return hold("UPSTREAM_CAPTURE_OR_QUOTE_REJECTED")
            ledger.append({"cut":now,"state":a["state"],"primary_sha256":pair[0],"secondary_sha256":pair[1],
                           "primary_clock_claim":dict(c["primary_clock"]),
                           "secondary_clock_claim":dict(c["secondary_clock"]),
                           "xg_claim":xg,"previous_digest":ledger[-1]["digest"] if ledger else None})
            ledger[-1]["digest"]=digest(ledger[-1])
            prior=a["state"];prev_xg=xg;prev_now=now;prior_clocks=clocks
            seen_pairs.add(pair);seen_primary.add(pair[0]);seen_secondary.add(pair[1])
        ctx=audit_context(context,prior,now)
        scenarios=sensitivity(prior,prematch,markets)
        return {**hold("MULTI_CUT_RESEARCH_ONLY"),"research_status":"RESEARCH_ONLY",
                "cut_count":len(ledger),"ledger_digest_unattested":ledger[-1]["digest"],
                "history_complete_verified":False,"provider_clock_claims_bound":True,
                "provider_upstream_clock_verified":False,"previous_forecast_rewrite_allowed":False,
                "actual_xg_verified":False,"xg_used_by_model":False,"actual_live_odds_verified":False,
                "model_edge":None,"verified_forward_sample_credit":0,
                "scenario_assumptions_not_calibrated":True,"scenario_count":len(scenarios),
                "scenarios":scenarios,"context_diagnostics":ctx,
                "quote_claim_count":len(out.get("quote_reviews",[]))}
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError,RecursionError):
        return hold("INVALID_MULTI_CUT_RESEARCH")
