"""Ingest real parsed FT feeds into source observations without invented kickoff times.

OpenFootball date-only records may be linked to a unique pre-sealed fixture
by exact team identities and UTC date, without inventing publisher kickoff.
"""
import argparse
import json
from datetime import datetime,timezone,timedelta
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
        rows=[];excluded_date_only=0;linked_date_only=0;ambiguous_date_only=0
        for item in source.get("records",[]):
            if not isinstance(item,dict) or item.get("status")!="FINISHED":continue
            # No kickoff time can be inferred from a date-only match.
            if "kickoff_utc" not in item:
                excluded_date_only+=1
                try:
                    home=team_id("bundesliga",item["home"])
                    away=team_id("bundesliga",item["away"])
                    day=datetime.fromisoformat(item["date"]).date()
                    candidates=[s for s in sealed if isinstance(s,dict) and s.get("league")=="bundesliga"
                        and team_id("bundesliga",s.get("home",""))==home
                        and team_id("bundesliga",s.get("away",""))==away
                        and datetime.fromisoformat(s["kickoff_utc"].replace("Z","+00:00")).astimezone(timezone.utc).date()==day]
                    if len(candidates)!=1:
                        if len(candidates)>1:ambiguous_date_only+=1
                        continue
                    s=candidates[0]
                    score=item["score_ft"]
                    ko=datetime.fromisoformat(s["kickoff_utc"].replace("Z","+00:00")).astimezone(timezone.utc)
                    if dt.astimezone(timezone.utc)<ko+timedelta(hours=2):
                        continue
                    if not isinstance(score,list) or len(score)!=2 or not all(type(x) is int and 0<=x<=30 for x in score):
                        continue
                    if not isinstance(s.get("fixture_id"),str) or not s["fixture_id"]:\n                        continue\n                    all_obs.append({"fixture_id":s["fixture_id"],"status":"FT",
                        "provider_id":provider,"independent_group_id":TRUSTED[provider],
                        "published_utc":dt.astimezone(timezone.utc).isoformat(),
                        "home_goals":score[0],"away_goals":score[1],
                        "source_url":source["source_url"],"raw_sha256":source["raw_sha256"],
                        "match_linkage":"EXACT_TEAMS_AND_DATE_ONLY","publisher_kickoff_utc":None})
                    linked_date_only+=1
                except (KeyError,TypeError,ValueError,AttributeError,OverflowError):
                    pass
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
        stats.append({"provider":provider,"accepted_observations":len(obs),"excluded_date_only_records":excluded_date_only,"date_only_unique_links":linked_date_only,"date_only_ambiguous":ambiguous_date_only})
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
