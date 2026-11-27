"""Opt-in private expansion of V45 historical candidate provenance.

Recover references from V32's original bounded archive observations. Verify
exact source bytes again. No retrospective forecasts or authenticated results.
"""
from collections import Counter
from datetime import timedelta
from .research_candidate_gap_v6 import stamp
from .research_missing_fixture_discovery_v16 import candidates,identity
from .research_historical_evidence_triage_v17 import bounded
from .research_archive_score_recovery_v14 import MAX_FILES as PRIMARY_MAX
from .research_two_publisher_recovery_v15 import MAX_FILES as SECONDARY_MAX
from .research_supplemental_history_v32 import inventory
from .research_integrated_fusion_v45 import history
from .research_live_intake_v4 import decode
from .research_prospective_fusion_v38 import sha,token,fingerprint,MAX_HISTORY
from .source_publish_guard import verify

def verify_ref(ref,k,score,archives,now):
    p=ref["provider"];sid=token(ref["provider_id"])
    digest=fingerprint(ref["decoded_sha256"])
    body=archives[(p,ref["path"],digest)]
    if sha(body)!=digest:raise ValueError("reference digest mismatch")
    d=decode(body)
    if p=="OpenLigaDB":
        if (d["schema"]!="football-king-openligadb-hourly-v1" or d["source"]!=p
            or d["production_recommendations"]!="DISABLED" or k[0]!="bundesliga"
            or not isinstance(d["matches"],list) or len(d["matches"])>100):
            raise ValueError("invalid primary reference")
        t=stamp(d["collected_utc"]);records=d["matches"];field="provider_match_id";status="FINISHED_CONFIRMED_BY_SOURCE"
    elif p=="thesportsdb":
        t=verify(d,now=now);records=[r for r in d["sampled_fixtures"] if r["provider"]==p]
        field="provider_event_id";status="FINISHED"
    else:raise ValueError("unknown reference publisher")
    if not k[3]+timedelta(minutes=90)<=t<=now or t!=stamp(ref["captured_utc"]):
        raise ValueError("reference clock mismatch")
    matches=[r for r in records if identity(r["league"],r["home"],r["away"],r["kickoff_utc"])==k]
    if len(matches)!=1:raise ValueError("ambiguous reference fixture")
    r=matches[0]
    if str(r[field])!=sid or r["status"]!=status or r["score_ft"]!=score:
        raise ValueError("reference fixture or score mismatch")
    return t

def expanded_history(raw,primary,secondary,*,as_of):
    now=stamp(as_of)
    a=bounded(primary,PRIMARY_MAX,now,"collected_utc")
    b=bounded(secondary,SECONDARY_MAX,now,"collected_utc")
    base,summary=history(raw,a,b,as_of=as_of)
    inv=inventory(raw,a,b,as_of=as_of,include_extra_references=True)
    if inv["ledger_sha256"]!=sha(raw) or inv["training_admission"] is not False:
        raise ValueError("supplemental ledger mismatch")
    if len(inv["extra_references"])!=inv["extra_prior_candidates"]:
        raise ValueError("supplemental roster mismatch")
    archives={(p,path,sha(body)):body for p,stream in (("OpenLigaDB",a),("thesportsdb",b)) for path,body in stream}
    ledger=candidates(raw);seen=set(ledger);extra=[];excluded=Counter()
    for c in inv["extra_references"]:
        k=c["key"];t=stamp(c["observed_utc"]);s=c["score"];refs=c["references"]
        if k in seen or identity(k[0],k[1],k[2],k[3].isoformat())!=k:
            raise ValueError("duplicate or unstable supplemental identity")
        seen.add(k)
        if not isinstance(s,list) or len(s)!=2 or any(type(x) is not int or not 0<=x<=30 for x in s):
            raise ValueError("invalid supplemental score")
        if not isinstance(refs,list) or len(refs) not in (1,2) or len({r["provider"] for r in refs})!=len(refs):
            raise ValueError("invalid supplemental reference roster")
        if max(verify_ref(r,k,s,archives,now) for r in refs)!=t:
            raise ValueError("supplemental final clock mismatch")
        if not t+timedelta(hours=24)<now:
            excluded["WITHIN_24H_DELAY"]+=1;continue
        last=max(refs,key=lambda r:(stamp(r["captured_utc"]),r["provider"]))
        extra.append(({"league":k[0],"home":k[1],"away":k[2],"kickoff_utc":k[3].isoformat(),
                       "observed_utc":t.isoformat(),"score":s,"source_id":last["provider"],
                       "fixture_id":last["provider_id"],"evidence_sha256":last["decoded_sha256"]},refs))
    combined=base+extra
    keys=[identity(r["league"],r["home"],r["away"],r["kickoff_utc"]) for r,_ in combined]
    ids=Counter((x["provider"],x["provider_id"]) for _,refs in combined for x in refs)
    slots=Counter((k[0],team,k[3]) for k in keys for team in k[1:3])
    accepted=[];base_count=extra_count=0
    for i,((item,refs),k) in enumerate(zip(combined,keys)):
        if any(ids[(x["provider"],x["provider_id"])]!=1 for x in refs) or any(slots[(k[0],team,k[3])]!=1 for team in k[1:3]):
            excluded["COMBINED_HISTORY_IDENTITY_CONFLICT"]+=1;continue
        accepted.append((item,refs))
        if i<len(base):base_count+=1
        else:extra_count+=1
    if len(accepted)>MAX_HISTORY:raise ValueError("combined history budget")
    return accepted,{**summary,"history_candidates":len(accepted),"dual_publisher_candidates":sum(len(r)==2 for _,r in accepted),
                     "supplemental_history_included":True,"original_history_candidates":base_count,
                     "supplemental_discovered":inv["extra_prior_candidates"],"supplemental_accepted":extra_count,
                     "supplemental_excluded":dict(excluded),"reference_bytes_rechecked":True,
                     "source_authenticity_verified":False,"authenticated_samples":0}
