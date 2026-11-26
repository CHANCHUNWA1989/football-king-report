"""Opt-in bounded real-file compatibility smoke test; no model scoring.

Downloads only pinned StatsBomb Open Data JSON via HTTPS. No credentials,
no raw files on disk, no published player/team metrics, no archive promotion.
Official usage terms must be reviewed before distribution of research results.
"""
import json
import sys
import hashlib
from urllib.request import Request,urlopen
from deep_handicap_historical_inputs import _decode,parse_event_structure,MAX_BYTES

ROOT="https://raw.githubusercontent.com/hudl/open-data/4b73468fc5b0f1950f9f66fada70ad3a4f9327cb/"
IDS=(3857276,3857271,3857296)
INDEX_LIMIT=2_000_000


def fetch(path,limit):
    url=ROOT+path
    req=Request(url,headers={"User-Agent":"FootballKingResearchCompatibility/1.0"})
    with urlopen(req,timeout=35) as response:
        if response.geturl()!=url:
            raise ValueError("UNEXPECTED_REDIRECT")
        raw=response.read(limit+1)
    if not 0<len(raw)<=limit:
        raise ValueError("DOWNLOAD_SIZE_LIMIT")
    return raw


def run():
    summary={"status":"HOLD","production_recommendations":"DISABLED",
             "data_source":"StatsBomb Open Data","attempted":0,
             "structural_pass":0,"failed":0,"true_forward_sample_count":0,
             "source_authenticated":False,"live_xg_verified":False,
             "model_inputs_enabled":False,"model_accuracy_verified":False}
    try:
        index=_decode(fetch("data/matches/43/106.json",INDEX_LIMIT),INDEX_LIMIT)
        if type(index) is not list or len(index)>1000:
            raise ValueError("BAD_INDEX")
        for mid in IDS:
            summary["attempted"]+=1
            try:
                matches=[m for m in index if type(m) is dict and m.get("match_id")==mid]
                if len(matches)!=1:
                    raise ValueError("BAD_MATCH_INDEX_IDENTITY")
                m=matches[0]
                if m.get("match_status")!="available" or m.get("competition_stage",{}).get("name")!="Group Stage":
                    raise ValueError("UNEXPECTED_MATCH_SCOPE")
                h=m["home_team"]["home_team_id"]
                a=m["away_team"]["away_team_id"]
                raw=fetch(f"data/events/{mid}.json",MAX_BYTES)
                count,features=parse_event_structure(raw,mid,h,a)
                # Do not emit player-level data or match-specific xG values.
                if count<=0 or not features["home_shots"]+features["away_shots"]:
                    raise ValueError("EMPTY_SHOT_FEATURES")
                summary["structural_pass"]+=1
                print(json.dumps({"match_id":mid,"sha256":hashlib.sha256(raw).hexdigest(),
                                  "compatibility":"PASS"}),flush=True)
            except Exception as exc:
                summary["failed"]+=1
                print(json.dumps({"match_id":mid,"compatibility":"FAIL",
                                  "error_type":type(exc).__name__}),flush=True)
    except Exception as exc:
        summary["index_error_type"]=type(exc).__name__
    print(json.dumps(summary),flush=True)
    return 0 if summary["structural_pass"]==len(IDS) else 1


if __name__=="__main__":
    sys.exit(run())
