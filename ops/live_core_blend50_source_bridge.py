"""Audit existing German and secondary snapshots against forward-capture gates.

The archived pair is a hint, not verified identity. Never emit seal inputs,
invent observation times, map names automatically, or claim source independence.
"""
import hashlib
import json
import subprocess
from collections import Counter,defaultdict
from datetime import timedelta
from live_core_blend50_forward_seal import instant,START,END
from research_strict_json import unique_object,reject_constant

GERMAN_PIN="8a06a5dd7d60e76cf54e04f4d6e81c8746bc06bf"
SECONDARY_PIN="324d5bc8c5b1a0c404f3251a40513fd88350001f"
MAX_BYTES=8_000_000
MAX_ROWS=10000

def decode(raw,pin):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_BYTES:raise ValueError("SOURCE_SIZE")
    if hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()!=pin:raise ValueError("BLOB_PIN_CHANGED")
    return json.loads(raw.decode("utf-8"),object_pairs_hook=unique_object,parse_constant=reject_constant)

def native(v):
    if type(v) is int and v>=0:v=str(v)
    if type(v) is not str or not 1<=len(v)<=160 or v!=v.strip() or not v.isascii() or not v.isdigit():
        raise ValueError("NATIVE_ID")
    return v

def rows(doc,key):
    v=doc[key]
    if type(v) is not list or len(v)>MAX_ROWS or any(type(r) is not dict for r in v):raise ValueError("ROW_SCOPE")
    return v

def inspect(g,s,*,now):
    if now.tzinfo is None:raise ValueError("NAIVE_NOW")
    if (g["schema"]!="football-king-openligadb-hourly-v1" or s["schema"]!="football-king-extra-source-audit-v1"
        or g["source"]!="OpenLigaDB" or g["production_recommendations"]!="DISABLED"
        or s["production_recommendations"]!="DISABLED"):raise ValueError("SOURCE_SCOPE")
    gt,st=instant(g["collected_utc"]),instant(s["collected_utc"])
    if max(gt,st)>now:raise ValueError("FUTURE_CAPTURE")
    gr,sr=rows(g,"matches"),rows(s,"sampled_fixtures")
    gi=defaultdict(list);si=defaultdict(list);claims=defaultdict(list)
    for r in gr:
        gi[native(r["provider_match_id"])].append(r)
        pair=r.get("source_id_pair")
        if pair is not None:
            if type(pair) is not dict:raise ValueError("PAIR_SCOPE")
            claims[native(pair["thesportsdb_event_id"])].append(r)
    for r in sr:
        if r.get("provider")=="thesportsdb":
            si[native(r["provider_event_id"])].append(r)
    count=Counter();reasons=Counter()
    for r in gr:
        if r["league"]!="bundesliga":
            count["outside_league_scope"]+=1;continue
        count["bundesliga_rows"]+=1
        pair=r.get("source_id_pair")
        if pair is None:
            count["no_pair_hint"]+=1;continue
        count["pair_hints"]+=1
        gid=native(r["provider_match_id"]);sid=native(pair["thesportsdb_event_id"])
        blocked=[]
        if (native(pair["openligadb_match_id"])!=gid
            or pair.get("pair_basis")!="LEAGUE_SCOPED_TEAMS_AND_KICKOFF"
            or r.get("crosscheck_state")!="TWO_PUBLISHER_KICKOFF_AGREEMENT"
            or r.get("crosscheck_provider")!="TheSportsDB"):
            blocked.append("PAIR_HINT_INCONSISTENT")
        candidates=si.get(sid,[])
        if len(gi[gid])!=1 or len(claims[sid])!=1 or len(candidates)>1:
            blocked.append("DUPLICATE_NATIVE_ID")
        if len(candidates)!=1:
            blocked.append("SECONDARY_ROW_NOT_UNIQUE")
        ko=instant(r["kickoff_utc"])
        if r.get("status")!="SCHEDULED" or r.get("score_ft") is not None:
            blocked.append("PRIMARY_NOT_PREMATCH")
        if len(candidates)==1:
            c=candidates[0]
            if c.get("league")!=r["league"] or instant(c["kickoff_utc"])!=ko:
                blocked.append("SECONDARY_LEAGUE_OR_KICKOFF_MISMATCH")
            if c.get("status")!="SCHEDULED" or c.get("score_ft") is not None:
                blocked.append("SECONDARY_NOT_PREMATCH")
            if any(type(z.get(k)) is not str or not z[k].strip() for z in (r,c) for k in ("home","away")):
                blocked.append("MISSING_TEAM_LABEL")
        if not blocked:count["pair_rows_structurally_consistent"]+=1
        # Collection timestamps are envelope clocks, not native observation
        # or provider publication clocks. A fresh envelope is necessary only.
        if now-gt>timedelta(hours=6):blocked.append("PRIMARY_ENVELOPE_STALE")
        if now-st>timedelta(hours=6):blocked.append("SECONDARY_ENVELOPE_STALE")
        if not START<=now<ko<END:blocked.append("OUTSIDE_PROTOCOL_WINDOW")
        if not timedelta(minutes=10)<=ko-now<=timedelta(hours=24):blocked.append("OUTSIDE_CAPTURE_WINDOW")
        if not blocked:count["timing_and_structure_candidates"]+=1
        blocked.extend(("CANONICAL_IDENTITY_NOT_AUTHENTICATED","NATIVE_OBSERVATION_TIME_UNVERIFIED",
                        "AUTHORIZED_COMPLETE_HISTORY_NOT_SUPPLIED"))
        reasons.update(blocked)
    for k in ("outside_league_scope","bundesliga_rows","no_pair_hint","pair_hints",
              "pair_rows_structurally_consistent","timing_and_structure_candidates"):count.setdefault(k,0)
    if len(gr)!=count["outside_league_scope"]+count["bundesliga_rows"] or count["bundesliga_rows"]!=count["no_pair_hint"]+count["pair_hints"]:
        raise ValueError("COUNT_MISMATCH")
    return {"primary_rows":len(gr),"secondary_rows":len(sr),"counts":dict(count),
            "overlapping_pair_blockers":dict(reasons),"checked_utc":now.isoformat(),
            "primary_collected_utc":gt.isoformat(),"secondary_collected_utc":st.isoformat(),
            "collection_envelope_clocks_only":True,"pair_hint_not_canonical_mapping":True,
            "global_fixture_coverage_complete":False,"seal_inputs_emitted":0,
            "authenticated_forward_samples":0,"actual_market_quotes_verified":False,
            "positive_ev_verified":False,"production_recommendations":"DISABLED","status":"HOLD"}

def replay():
    g=decode(subprocess.check_output(["git","cat-file","blob",GERMAN_PIN],timeout=10),GERMAN_PIN)
    s=decode(subprocess.check_output(["git","cat-file","blob",SECONDARY_PIN],timeout=10),SECONDARY_PIN)
    # Rehearse at the later archived collection envelope time, not wall clock.
    now=max(instant(g["collected_utc"]),instant(s["collected_utc"]))
    return {"primary_blob":GERMAN_PIN,"secondary_blob":SECONDARY_PIN,
            "retrospective_archive_review":True,"actual_live_collection":False,**inspect(g,s,now=now)}
if __name__=="__main__":
    print(json.dumps(replay(),sort_keys=True,allow_nan=False))
