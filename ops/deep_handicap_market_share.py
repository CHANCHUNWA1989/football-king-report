"""Private settlement-weighted market comparison; no betting authorization."""
import math
import statistics
from collections import defaultdict
from asian_handicap_research import TYPES
from deep_handicap_private_capture import capture

SCHEMA = "football-king-dhe-market-share-research-v1"


def effective_share(p):
    """Winning stake divided by stake not returned as push, in expectation."""
    if type(p) is not dict or set(p) != set(TYPES):
        raise ValueError("BAD_GRADE_DISTRIBUTION")
    if any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=1 for x in p.values()):
        raise ValueError("BAD_GRADE_DISTRIBUTION")
    if abs(math.fsum(p.values())-1)>1e-8:
        raise ValueError("BAD_GRADE_MASS")
    w=p["FULL_WIN"]+.5*p["HALF_WIN"]
    l=p["FULL_LOSS"]+.5*p["HALF_LOSS"]
    if w+l<=1e-12:
        raise ValueError("NO_DECISIVE_STAKE")
    return w/(w+l)


def compare(shadow, quote_report, *, now):
    """Recompute same-cutoff candidate. Never infer verified market bias."""
    out={"schema":SCHEMA,"status":"HOLD","production_recommendations":"DISABLED",
         "research_only":True,"private_output_only":True,
         "source_authenticated":False,"bookmaker_independence_verified":False,
         "market_bias_verified":False,"model_calibration_verified":False,
         "true_forward_sample_count":0,"qualifies_for_betting":False,
         "positive_expected_value_verified":False,"raw_quotes_emitted":False,
         "private_diagnostics":None}
    try:
        report=capture(shadow,quote_report,now=now)
        c=report.get("candidate")
        if c is None:
            raise ValueError("PREMATCH_CANDIDATE_GATE_REJECTED")
        fav=quote_report["home"] if c["side"]=="HOME" else quote_report["away"]
        groups=defaultdict(dict)
        for q in quote_report["quotes"]:
            if q["market"]!="spreads":
                continue
            side="FAVOURITE" if q["outcome"]==fav else "OTHER"
            g=groups[q["bookmaker"]]
            if side in g:
                raise ValueError("DUPLICATE_BOOK_SIDE")
            g[side]=q["decimal_odds"]
        if not 2<=len(groups)<=60:
            raise ValueError("INSUFFICIENT_OR_EXCESS_BOOK_COUNT")
        shares=[]
        for g in groups.values():
            if set(g)!={"FAVOURITE","OTHER"}:
                raise ValueError("INCOMPLETE_BOOK_PAIR")
            f,o=1/g["FAVOURITE"],1/g["OTHER"]
            mass=f+o
            if not 1-1e-12<=mass<=1.25:
                raise ValueError("PRICE_PAIR_MARGIN_OUTSIDE_POLICY")
            shares.append(f/mass)
        market=statistics.median(shares)
        model={}
        for name in ("baseline","challenger"):
            p=c[name]["probabilities"]
            eff=effective_share(p)
            model[name]={"full_win_probability":p["FULL_WIN"],
                         "settlement_weighted_share":eff,
                         "share_minus_market_proxy":eff-market}
        out.update(reason="PRIVATE_DESCRIPTIVE_MARKET_SHARE_COMPARISON",
                   candidate_sha256=report["candidate_sha256"],
                   book_pair_count=len(groups),
                   private_diagnostics={"normalized_inverse_price_share_median":market,
                       "book_share_range":{"min":min(shares),"max":max(shares)},
                       "models":model},
                   price_normalization_assumption="PROPORTIONAL_TWO_SIDE_MARGIN_REMOVAL",
                   not_full_win_probability=True)
    except (ValueError,TypeError,KeyError,OverflowError,AttributeError) as exc:
        allowed={"PREMATCH_CANDIDATE_GATE_REJECTED","DUPLICATE_BOOK_SIDE",
                 "INSUFFICIENT_OR_EXCESS_BOOK_COUNT","INCOMPLETE_BOOK_PAIR",
                 "PRICE_PAIR_MARGIN_OUTSIDE_POLICY","BAD_GRADE_DISTRIBUTION",
                 "BAD_GRADE_MASS","NO_DECISIVE_STAKE"}
        out["reason"]=str(exc) if str(exc) in allowed else "INVALID_PRIVATE_INPUT"
    return out
