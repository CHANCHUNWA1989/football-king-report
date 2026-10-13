"""Check raw external pages for fixture text; not a score parser or verifier."""
import argparse
import hashlib
import json
import re
from html import unescape
from pathlib import Path

def probe(folder, queue):
    folder=Path(folder)
    manifest=json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status")!="HOLD" or manifest.get("eligible_for_model_scoring") is not False:
        raise ValueError("UNSAFE_MANIFEST")
    fixtures=json.loads(Path(queue).read_text(encoding="utf-8")).get("matured_unmatched_fixtures",[])
    results=[]
    for source in manifest["sources"]:
        if source.get("status")!="FETCHED_UNVERIFIED":
            continue
        raw=(folder/source["raw_file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=source["raw_sha256"]:
            raise ValueError("RAW_HASH_MISMATCH")
        html=unescape(raw.decode("utf-8",errors="replace"))
        text=re.sub(r"(?is)<(script|style)[^>]*>.*?</\\1>"," ",html)
        text=re.sub(r"(?s)<[^>]*>"," ",text)
        text=re.sub(r"\\s+"," ",text).casefold()
        found=[]
        for fixture in fixtures:
            home=fixture["home"].casefold()
            away=fixture["away"].casefold()
            found.append({"fixture_id":fixture["fixture_id"],"home_text_present":home in text,"away_text_present":away in text})
        results.append({"provider":source["provider"],"fixture_text_checks":found,
                        "both_names_present":sum(x["home_text_present"] and x["away_text_present"] for x in found)})
    return {"status":"HOLD","eligible_for_model_scoring":False,"independently_verified":False,
            "production_recommendations":"DISABLED","source_probes":results}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--raw-dir",required=True)
    p.add_argument("--coverage",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    result=probe(a.raw_dir,a.coverage)
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\\n",encoding="utf-8")
    print("EXTERNAL TEXT PROBE",[(s["provider"],s["both_names_present"]) for s in result["source_probes"]])

if __name__=="__main__":main()
