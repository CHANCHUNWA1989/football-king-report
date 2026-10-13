"""Parse raw Bundesliga feeds into auditable, still-unverified FT candidates.

Raw publisher payloads are never treated as independently verified results.
"""
import argparse
import hashlib
import json
from pathlib import Path

def parse_openligadb(payload):
    if not isinstance(payload,list): raise ValueError("INVALID_OPENLIGADB")
    out=[]
    for m in payload:
        if not isinstance(m,dict) or not m.get("matchIsFinished"):continue
        try:
            scores=m["matchResults"]
            finals=[x for x in scores if x.get("resultTypeID")==2]
            if len(finals)!=1:continue
            ft=finals[0]
            out.append({"home":m["team1"]["teamName"],"away":m["team2"]["teamName"],
                "kickoff_utc":m["matchDateTimeUTC"]+"Z" if not m["matchDateTimeUTC"].endswith("Z") else m["matchDateTimeUTC"],
                "score_ft":[ft["pointsTeam1"],ft["pointsTeam2"]],"status":"FINISHED"})
        except (KeyError,TypeError,AttributeError):continue
    return out

def parse_openfootball(payload):
    if not isinstance(payload,dict) or not isinstance(payload.get("matches"),list):raise ValueError("INVALID_OPENFOOTBALL")
    out=[]
    for m in payload["matches"]:
        if not isinstance(m,dict):continue
        try:
            score=m["score"]["ft"]
            if not isinstance(score,list) or len(score)!=2 or any(type(x) is not int or x<0 or x>30 for x in score):continue
            out.append({"home":m["team1"],"away":m["team2"],"date":m["date"],
                        "score_ft":score,"status":"FINISHED"})
        except (KeyError,TypeError):continue
    return out

def convert(folder):
    folder=Path(folder)
    manifest=json.loads((folder/"manifest.json").read_text())
    if manifest.get("status")!="HOLD" or manifest.get("independently_verified") is not False:
        raise ValueError("UNSAFE_MANIFEST")
    out=[]
    parsers={"OpenLigaDB":parse_openligadb,"OpenFootball":parse_openfootball}
    for source in manifest.get("sources",[]):
        if source.get("status")!="FETCHED_UNVERIFIED":continue
        provider=source["provider"]
        if provider not in parsers:continue
        expected_file=provider.lower()+".json"
        if source.get("raw_file")!=expected_file:
            raise ValueError("UNSAFE_RAW_FILE_PATH")
        raw=(folder/expected_file).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=source["raw_sha256"]:
            raise ValueError("RAW_HASH_MISMATCH")
        records=parsers[provider](json.loads(raw))
        out.append({"provider":provider,"source_url":source["source_url"],
                    "raw_sha256":source["raw_sha256"],"captured_utc":manifest["captured_utc"],
                    "records":records,"independently_verified":False})
    return {"status":"HOLD","production_recommendations":"DISABLED",
            "sources":out,"independently_verified":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--raw-dir",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    Path(a.output).write_text(json.dumps(convert(a.raw_dir),ensure_ascii=False,indent=2)+"\n")
if __name__=="__main__":main()
