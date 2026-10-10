"""Cross-bookmaker consensus diagnostics on validated, same-line odds.

Research-only. Do not interpret a consensus or outlier as positive EV.
"""
import json
import math
from collections import defaultdict
from pathlib import Path

SCHEMA="football-king-market-consensus-v1"


def analyze(audit, *, min_bookmakers=2, max_spread_ratio=1.25):
    if (not isinstance(audit,dict) or not isinstance(audit.get("quotes"),list)
            or audit.get("production_recommendations", "DISABLED") != "DISABLED"):
        raise ValueError("INVALID_QUOTE_AUDIT")
    if type(min_bookmakers) is not int or not 2<=min_bookmakers<=10:
        raise ValueError("INVALID_BOOKMAKER_THRESHOLD")
    if type(max_spread_ratio) not in (float,int) or not 1<=max_spread_ratio<=3:
        raise ValueError("INVALID_DISPERSION_THRESHOLD")
    grouped=defaultdict(dict)
    invalid=0
    for q in audit["quotes"]:
        if not isinstance(q,dict):
            invalid+=1
            continue
        book=q.get("bookmaker")
        price=q.get("decimal_odds")
        if (q.get("status")!="FRESH_OBSERVATION_NOT_EXECUTABLE"
            or not isinstance(book,str) or not book
            or type(price) not in (float,int) or not math.isfinite(price)
            or not 1.01<=price<=100
            or q.get("market") not in ("h2h","totals","spreads")
            or not isinstance(q.get("event_id"),str) or not q["event_id"].strip()
            or not isinstance(q.get("outcome"),str) or not q["outcome"].strip()
            or not isinstance(q.get("market_last_update_utc"),str)):

            invalid+=1
            continue
        point=q.get("point")
        if point is not None and (type(point) not in (float,int) or not math.isfinite(point)):
            invalid+=1
            continue
        # Never combine pre-match and in-play prices in one consensus.
        # Legacy audit fixtures lacking phase remain explicitly UNKNOWN.
        prematch=q.get("quote_pre_match_at_capture")
        phase=q.get("market_phase_at_capture")
        if prematch is True and phase=="PREMATCH":
            phase_group="PREMATCH"
        elif prematch is False and phase=="IN_PLAY_OR_TOO_LATE":
            phase_group="IN_PLAY_OR_TOO_LATE"
        elif prematch is None and phase is None:
            phase_group="UNKNOWN"
        else:
            invalid+=1
            continue
        key=(q["event_id"],q["market"],q["outcome"],point,phase_group)
        # Duplicate quotes from the same bookmaker cannot inflate consensus.
        if book in grouped[key]:
            invalid+=1
            continue
        grouped[key][book]=price
    rows=[]
    for (event,market,outcome,point,phase_group),books in sorted(
        grouped.items(),key=lambda x:(str(x[0][0]),str(x[0][1]),str(x[0][2]),str(x[0][3]))):
        prices=sorted(books.values())
        n=len(prices)
        mid=(prices[(n-1)//2]+prices[n//2])/2
        ratio=prices[-1]/prices[0]
        enough=n>=min_bookmakers
        consistent=ratio<=max_spread_ratio
        rows.append({
            "event_id":event,"market":market,"outcome":outcome,"point":point,
            "market_phase_at_capture":phase_group,
            "prematch_consensus_authenticated":False,
            "bookmakers":n,"min_decimal_odds":prices[0],
            "median_decimal_odds":round(mid,4),
            "max_decimal_odds":prices[-1],
            "max_to_min_ratio":round(ratio,4),
            "consensus_status":(
                "RESEARCH_CONSENSUS" if enough and consistent
                else "DISAGREEMENT_HOLD" if enough else "INSUFFICIENT_BOOKMAKERS"),
            "bookmaker_quotes":dict(sorted(books.items())),
            "independent_provider_confirmed":False,
            "positive_ev_proven":False,
        })
    return {"schema":SCHEMA,"status":"RESEARCH_ONLY" if rows else "HOLD",
            "groups":rows,"invalid_or_duplicate_quotes":invalid,
            "groups_with_research_consensus":sum(
                x["consensus_status"]=="RESEARCH_CONSENSUS" for x in rows),
            "independent_provider_confirmed":False,
            "model_probability_verified":False,
            "production_recommendations":"DISABLED","recommendation":None}


def main(argv=None):
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output",default="market-consensus-audit.json")
    args=p.parse_args(argv)
    from market_quote_gate import SCHEMA as QUOTE_SCHEMA
    audit=json.loads(Path(args.input).read_text(encoding="utf-8"))
    if audit.get("schema")!=QUOTE_SCHEMA:
        raise ValueError("WRONG_QUOTE_AUDIT_SCHEMA")
    report=analyze(audit)
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":report["status"],"groups":len(report["groups"]),
                      "consensus":report["groups_with_research_consensus"],
                      "production_recommendations":"DISABLED"}))


if __name__=="__main__":
    main()
