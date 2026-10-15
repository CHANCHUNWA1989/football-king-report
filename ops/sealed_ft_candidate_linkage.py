"""Link date-only cross-publisher FT agreement to archived fixtures conservatively.

A diagnostic link is NOT independently attested FT and cannot score models.
"""
import argparse
import json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from cross_source_ft_diagnostic import name_key
from fixture_identity_audit import conflicting_fixture_ids

def link(sealed,diagnostic):
    if not isinstance(sealed,list) or not isinstance(diagnostic,dict):
        raise ValueError("INVALID_INPUT")
    if diagnostic.get("schema")!="football-king-cross-source-ft-diagnostic-v1" or diagnostic.get("independently_verified") is not False:
        raise ValueError("UNSAFE_DIAGNOSTIC")
    if diagnostic.get("external_provenance_rechecked") is not False or diagnostic.get("production_recommendations")!="DISABLED":
        raise ValueError("UNSAFE_DIAGNOSTIC")
    conflicting_ids=set(conflicting_fixture_ids(sealed))
    archive={}
    for row in sealed:
        if not isinstance(row,dict) or row.get("production_recommendations")!="DISABLED":
            raise ValueError("UNSAFE_SEALED")
        try:
            dt=datetime.fromisoformat(row["kickoff_utc"].replace("Z","+00:00"))
            if dt.tzinfo is None:continue
            key=(dt.astimezone(timezone.utc).date().isoformat(),name_key(row["home"]),name_key(row["away"]))
            archive.setdefault(key,[]).append(row)
        except (KeyError,ValueError,TypeError,AttributeError):
            continue
    links=[];ambiguous=0;unmatched=0
    unique_fixture_ids={row.get("fixture_id") for rows in archive.values() for row in rows if isinstance(row.get("fixture_id"),str)}
    archive_dates_count=len({key[0] for key in archive})
    duplicate_fixture_archive_rows=max(0,sum(len(rows) for rows in archive.values())-len(unique_fixture_ids))
    seen_fixture_ids=set()
    archive_dates={key[0] for key in archive}
    archive_teams={(key[1],key[2]) for key in archive}
    blockers=Counter()
    agreements=diagnostic.get("agreements",[])
    if not isinstance(agreements,list):
        raise ValueError("INVALID_AGREEMENTS")
    for item in agreements:
        if not isinstance(item,dict):continue
        key=(item.get("match_date"),name_key(item.get("home")),name_key(item.get("away")))
        matches=archive.get(key,[])
        unique_matches={}
        for candidate in matches:
            fixture_id=candidate.get("fixture_id")
            if isinstance(fixture_id,str) and fixture_id:
                unique_matches.setdefault(fixture_id,candidate)
        if len(unique_matches)!=1:
            ambiguous+=int(len(unique_matches)>1 or (len(matches)>0 and not unique_matches))
            unmatched+=int(len(matches)==0)
            if len(unique_matches)>1 or (len(matches)>0 and not unique_matches):
                blockers['AMBIGUOUS_SEALED_FIXTURE']+=1
            elif key[0] not in archive_dates:
                blockers['NO_ARCHIVED_FIXTURE_ON_DATE']+=1
            elif (key[1],key[2]) not in archive_teams:
                blockers['NO_EXACT_TEAM_PAIR']+=1
            else:
                blockers['DATE_AND_TEAM_PAIR_DO_NOT_ALIGN']+=1
            continue
        row=next(iter(unique_matches.values()))
        if row["fixture_id"] in conflicting_ids:
            blockers["CONFLICTING_FIXTURE_IDENTITY"]+=1
            continue
        score=item.get("openliga_score")
        if (not isinstance(score,list) or len(score)!=2 or
            any(type(v) is not int or v<0 or v>30 for v in score)):
            blockers["INVALID_FT_SCORE"]+=1
            continue
        if score!=item.get("openfootball_score"):
            blockers["SCORE_DISAGREEMENT_IN_AGREEMENTS"]+=1
            continue
        if row["fixture_id"] in seen_fixture_ids:
            blockers["DUPLICATE_SOURCE_AGREEMENT"]+=1
            continue
        seen_fixture_ids.add(row["fixture_id"])
        links.append({"fixture_id":row["fixture_id"],"match_date":key[0],
          "score_ft":item["openliga_score"],"source_urls":item.get("source_urls",[]),
          "raw_sha256":item.get("raw_sha256",[]),"link_status":"CANDIDATE_ONLY",
          "kickoff_precision":"DATE_ONLY","independently_verified":False})
    return {"schema":"football-king-sealed-ft-linkage-v1","status":"RESEARCH_ONLY",
      "candidate_link_count":len(links),"ambiguous_sealed_keys":ambiguous,
      "unmatched_agreements":unmatched,"link_blockers":dict(sorted(blockers.items())),
      "archive_fixture_count":len(sealed),"unique_archive_fixture_count":len(unique_fixture_ids),
      "archive_date_count":archive_dates_count,"duplicate_fixture_archive_rows":duplicate_fixture_archive_rows,"source_agreement_count":len(diagnostic.get("agreements",[])),
      "links":links,
      "external_provenance_rechecked":False,"independently_verified":False,
      "eligible_for_model_scoring":False,"production_recommendations":"DISABLED"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--sealed",required=True);p.add_argument("--diagnostic",required=True);p.add_argument("--output",required=True)
    a=p.parse_args()
    result=link(json.loads(Path(a.sealed).read_text(encoding="utf-8")),
                json.loads(Path(a.diagnostic).read_text(encoding="utf-8")))
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Research-only sealed FT candidate links:",result["candidate_link_count"])
if __name__=="__main__":
    main()
