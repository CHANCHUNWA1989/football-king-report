"""Provenance-preserving conversion of a single real FT provider feed.

One provider alone can NEVER certify a result. This module only creates
observations, requiring an explicit publisher ID, independent origin group,
and captured timestamp supplied by the collector. No inferred independence.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

def utc(value):
    dt=datetime.fromisoformat(value.replace("Z","+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timezone required")
    return dt.astimezone(timezone.utc)

def observations(sealed_rows, source_rows, provider_id, group_id, published_utc):
    if not provider_id or not group_id or not isinstance(sealed_rows,list) or not isinstance(source_rows,list):
        raise ValueError("invalid provenance or input")
    captured=utc(published_utc)
    output=[]
    for sealed in sealed_rows:
        if not isinstance(sealed,dict):
            continue
        try:
            ko=utc(sealed["kickoff_utc"])
            if captured <= ko:
                continue
            matches=[]
            for row in source_rows:
                if not isinstance(row,dict) or row.get("status") not in ("FT","FINISHED"):
                    continue
                if row.get("league")!=sealed.get("league") or row.get("home")!=sealed.get("home") or row.get("away")!=sealed.get("away"):
                    continue
                if abs((utc(row["kickoff_utc"])-ko).total_seconds())>60:
                    continue
                score=row["score_ft"]
                if not isinstance(score,list) or len(score)!=2 or not all(type(x) is int and 0<=x<=30 for x in score):
                    continue
                matches.append(tuple(score))
            if len(matches)!=1:
                continue
            home,away=matches[0]
            output.append({"fixture_id":sealed["fixture_id"],"status":"FT",
                "provider_id":provider_id,"independent_group_id":group_id,
                "published_utc":captured.isoformat(),
                "home_goals":home,"away_goals":away})
        except (KeyError,TypeError,ValueError,AttributeError,OverflowError):
            continue
    return output

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--sealed",required=True)
    p.add_argument("--source",required=True)
    p.add_argument("--provider",required=True)
    p.add_argument("--origin-group",required=True)
    p.add_argument("--published-utc",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    sealed=json.loads(Path(a.sealed).read_text(encoding="utf-8"))
    rows=json.loads(Path(a.source).read_text(encoding="utf-8"))
    output=observations(sealed,rows,a.provider,a.origin_group,a.published_utc)
    Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    Path(a.output).write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

if __name__=="__main__":
    main()
