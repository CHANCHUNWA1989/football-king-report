"""Explain why real sealed fixtures do not link to parsed FT evidence.

Diagnostics only: no score certification, probability scoring or recommendation.
"""
import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from team_identity import team_id

def _day(value):
    try:
        dt=datetime.fromisoformat(value.replace("Z","+00:00"))
        return dt.astimezone(timezone.utc).date().isoformat() if dt.tzinfo else None
    except (AttributeError,ValueError,TypeError,OverflowError):
        return None

def diagnose(sealed,parsed):
    if not isinstance(sealed,list) or not isinstance(parsed,dict):
        raise ValueError("INVALID_INPUT")
    if parsed.get("status")!="HOLD" or parsed.get("independently_verified") is not False:
        raise ValueError("UNSAFE_SOURCE_BUNDLE")
    sources=parsed.get("sources",[])
    if not isinstance(sources,list):
        raise ValueError("INVALID_SOURCES")
    indexed={}
    for source in sources:
        if not isinstance(source,dict):continue
        provider=source.get("provider")
        if provider not in ("OpenLigaDB","OpenFootball"):continue
        entries=[]
        for rec in source.get("records",[]):
            if not isinstance(rec,dict) or rec.get("status")!="FINISHED":continue
            h=team_id("bundesliga",rec.get("home",""))
            a=team_id("bundesliga",rec.get("away",""))
            day=rec.get("date") if isinstance(rec.get("date"),str) else _day(rec.get("kickoff_utc"))
            if h and a and h!=a and day:
                entries.append((h,a,day,rec))
        indexed[provider]=entries
    report=[]
    reasons=Counter()
    for row in sealed:
        if not isinstance(row,dict) or row.get("league")!="bundesliga":continue
        h=team_id("bundesliga",row.get("home",""))
        a=team_id("bundesliga",row.get("away",""))
        day=_day(row.get("kickoff_utc"))
        if not h or not a or h==a or not day:continue
        evidence={}
        for provider,entries in indexed.items():
            same_teams=[rec for hh,aa,dd,rec in entries if hh==h and aa==a]
            same_date=[rec for hh,aa,dd,rec in entries if hh==h and aa==a and dd==day]
            other_dates=sorted({rec.get("date") or _day(rec.get("kickoff_utc")) for rec in same_teams if rec not in same_date})
            evidence[provider]={"exact_team_and_utc_date":len(same_date),"same_teams_other_dates":other_dates,
                                "ambiguous":len(same_date)>1}
        counts=[v["exact_team_and_utc_date"] for v in evidence.values()]
        if len(counts)==2 and all(n==1 for n in counts):
            left=indexed["OpenLigaDB"];right=indexed["OpenFootball"]
            scores=[]
            for entries in (left,right):
                scores.extend(tuple(rec.get("score_ft",[])) for hh,aa,dd,rec in entries if (hh,aa,dd)==(h,a,day))
            reason="TWO_SOURCE_SCORE_AGREEMENT_CANDIDATE" if len(scores)==2 and scores[0]==scores[1] else "TWO_SOURCE_SCORE_CONFLICT"
        elif any(n>1 for n in counts):reason="AMBIGUOUS_MATCHES"
        elif any(n==1 for n in counts):reason="SINGLE_SOURCE_ONLY"
        else:reason="NO_MATCHING_SOURCE_DATE"
        reasons[reason]+=1
        report.append({"fixture_id":row.get("fixture_id"),"kickoff_date_utc":day,"reason":reason,"providers":evidence})
    return {"status":"HOLD","production_recommendations":"DISABLED","independently_verified":False,
            "diagnostic_only":True,"sealed_bundesliga_examined":len(report),
            "reason_counts":dict(sorted(reasons.items())),"fixtures":report}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--sealed",required=True)
    p.add_argument("--parsed",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    out=diagnose(json.loads(Path(a.sealed).read_text()),json.loads(Path(a.parsed).read_text()))
    target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
    print("FT LINKAGE DIAGNOSTICS",out["reason_counts"])

if __name__=="__main__":main()
