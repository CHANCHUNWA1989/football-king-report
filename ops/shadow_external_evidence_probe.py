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
    MAX_NAME_DISTANCE=1200
    source_hits={}
    for source in manifest["sources"]:
        if source.get("status")!="FETCHED_UNVERIFIED":
            continue
        raw=(folder/source["raw_file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=source["raw_sha256"]:
            raise ValueError("RAW_HASH_MISMATCH")
        html=unescape(raw.decode("utf-8",errors="replace"))
        text=re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>"," ",html)
        text=re.sub(r"(?s)<[^>]*>"," ",text)
        text=re.sub(r"\s+"," ",text).casefold()
        found=[]
        for fixture in fixtures:
            home=fixture["home"].casefold()
            away=fixture["away"].casefold()
            home_positions=[m.start() for m in re.finditer(re.escape(home),text)]
            away_positions=[m.start() for m in re.finditer(re.escape(away),text)]
            close_pairs=sorted((abs(h-a),h,a) for h in home_positions for a in away_positions if abs(h-a)<=MAX_NAME_DISTANCE)
            near=bool(close_pairs)
            snippet=None
            if near:
                _,hp,ap=close_pairs[0]
                snippet=text[max(0,min(hp,ap)-100):max(hp+len(home),ap+len(away))+100][:1500]
            found.append({"fixture_id":fixture["fixture_id"],"home_text_present":bool(home_positions),"away_text_present":bool(away_positions),"names_nearby":near,"nearest_name_distance":close_pairs[0][0] if near else None,"context_excerpt":snippet})
        source_hits[source["provider"]]={x["fixture_id"] for x in found if x["names_nearby"]}
        results.append({"provider":source["provider"],"fixture_text_checks":found,
                        "both_names_present":sum(x["home_text_present"] and x["away_text_present"] for x in found),"names_nearby":sum(x["names_nearby"] for x in found)})
    overlap=sorted(set.intersection(*source_hits.values())) if len(source_hits)>=2 else []
    return {"status":"HOLD","eligible_for_model_scoring":False,"independently_verified":False,
            "production_recommendations":"DISABLED","source_probes":results,"max_name_distance_chars":MAX_NAME_DISTANCE,"both_sources_name_overlap_fixture_ids":overlap,"both_sources_name_overlap_count":len(overlap)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--raw-dir",required=True)
    p.add_argument("--coverage",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    result=probe(a.raw_dir,a.coverage)
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("EXTERNAL TEXT PROBE",[(s["provider"],s["both_names_present"],[x["fixture_id"] for x in s["fixture_text_checks"] if x["home_text_present"] and x["away_text_present"]]) for s in result["source_probes"]])
    print("EXTERNAL NAME OVERLAP (NOT SCORES)",result["both_sources_name_overlap_count"],result["both_sources_name_overlap_fixture_ids"])

if __name__=="__main__":main()
