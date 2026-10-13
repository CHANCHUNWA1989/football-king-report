"""Ingest real parsed FT feeds into source observations without invented kickoff times.

OpenFootball date-only records are deliberately excluded until fixture-level
kickoff can be independently established from that publisher's raw feed.
"""
import argparse
import json
from datetime import datetime,timezone
from pathlib import Path
from shadow_ft_observation_bridge import observations
from team_identity import team_id
from shadow_verified_adapter import trusted_origin

TRUSTED={"OpenLigaDB":"openligadb","OpenFootball":"openfootball"}

def ingest(sealed,parsed):
    if not isinstance(sealed,list) or parsed.get("status")!="HOLD" or parsed.get("independently_verified") is not False or parsed.get("production_recommendations")!="DISABLED":
        raise ValueError("UNSAFE_INPUT")
    all_obs=[];stats=[]
    seen=set()
    for source in parsed.get("sources",[]):
        provider=source.get("provider")
        if provider not in TRUSTED or provider in seen:
            raise ValueError("INVALID_OR_DUPLICATE_PROVIDER")
        seen.add(provider)
        if not trusted_origin(provider,source.get("source_url")):
            raise ValueError("UNTRUSTED_PUBLISHER_ORIGIN")
        digest=source.get("raw_sha256")
        if not isinstance(digest,str) or len(digest)!=64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError("INVALID_SOURCE_DIGEST")
        captured=source.get("captured_utc")
        dt=datetime.fromisoformat(captured.replace("Z","+00:00"))
        if dt.tzinfo is None:raise ValueError("NAIVE_CAPTURE_TIME")
        if dt.utcoffset().total_seconds()!=0:dt=dt.astimezone(timezone.utc)
        rows=[];excluded_date_only=0
        for item in source.get("records",[]):
            if not isinstance(item,dict) or item.get("status")!="FINISHED":continue
            # No kickoff time can be inferred from a date-only match.
            if "kickoff_utc" not in item:
                excluded_date_only+=1
                continue
            home=team_id("bundesliga",item.get("home",""))
            away=team_id("bundesliga",item.get("away",""))
            if not home or not away or home==away:continue
            for s in sealed:
                if (isinstance(s,dict) and s.get("league")=="bundesliga"
                    and team_id("bundesliga",s.get("home",""))==home
                    and team_id("bundesliga",s.get("away",""))==away):
                    rows.append({"league":"bundesliga","home":s["home"],"away":s["away"],
                                 "kickoff_utc":item["kickoff_utc"],"score_ft":item.get("score_ft"),
                                 "status":"FINISHED","source_url":source["source_url"],
                                 "raw_sha256":source["raw_sha256"]})
        obs=observations(sealed,rows,provider,TRUSTED[provider],captured)
        all_obs.extend(obs)
        stats.append({"provider":provider,"accepted_observations":len(obs),"excluded_date_only_records":excluded_date_only})
    return {"status":"HOLD","independently_verified":False,"production_recommendations":"DISABLED",
            "observations":all_obs,"source_stats":stats,"note":"Observations are single-publisher claims, not verified FT; two independent eligible origins must agree."}

def main():
    p=argparse.ArgumentParser()
    for x in ("sealed","parsed","output"):p.add_argument("--"+x,required=True)
    a=p.parse_args()
    out=ingest(json.loads(Path(a.sealed).read_text()),json.loads(Path(a.parsed).read_text()))
    path=Path(a.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
    print("GENUINE SOURCE OBSERVATIONS",out["source_stats"],"total",len(out["observations"]))

if __name__=="__main__":main()
