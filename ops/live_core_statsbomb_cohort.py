"""Private bounded StatsBomb 2022 World Cup cohort audit; no live calibration.

Source: StatsBomb Open Data (https://github.com/hudl/open-data).
Respect attribution/logo and use terms before distributing derived results.
No network, no source payloads in Git, no automatic promotion.
"""
import hashlib
import json
from pathlib import Path
from collections import defaultdict
from live_core_statsbomb_event_replay import decode,replay,clock,native,MAX
from research_strict_json import unique_object,reject_constant

INDEX_PIN="7e259140298f3de247ab94f1f4e026619c0f612b"
INDEX_COUNT=64


def load(root,name,limit):
    path=root/name
    if path.is_symlink() or not path.is_file():
        raise ValueError("PRIVATE_FILE")
    with path.open("rb") as f:
        raw=f.read(limit+1)
    if not 0<len(raw)<=limit:raise ValueError("SIZE")
    return raw


def index(raw):
    pin=hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()
    if pin!=INDEX_PIN:raise ValueError("INDEX_PIN")
    d=json.loads(raw.decode(),object_pairs_hook=unique_object,parse_constant=reject_constant)
    if type(d) is not list or len(d)!=INDEX_COUNT:raise ValueError("INDEX_SCOPE")
    rows=[]
    for m in d:
        mid=native(m["match_id"])
        h=native(m["home_team"]["home_team_id"]);a=native(m["away_team"]["away_team_id"])
        if h==a or not "2022-11-20"<=m["match_date"]<="2022-12-18":
            raise ValueError("INDEX_FIXTURE")
        rows.append((m["match_date"],mid,h,a))
    if len({r[1] for r in rows})!=len(rows):raise ValueError("DUPLICATE_MATCH")
    return sorted(rows)


def inspect(raw,pin,h,a):
    events=decode(raw,pin)
    out=replay(events,h,a)
    ends={p:{clock(e["timestamp"]) for e in events if e["period"]==p and e["type"]["name"]=="Half End"} for p in (1,2)}
    if any(len(v)!=1 for v in ends.values()):raise ValueError("PERIOD_END")
    durations=[next(iter(ends[p]))/60000 for p in (1,2)]
    if any(v<45 for v in durations):raise ValueError("SHORT_PERIOD")
    return {"buckets":out["buckets"],"regulation_cards":out["regulation_cards"],
            "elapsed_minutes_by_half":durations,
            "elapsed_beyond_45_by_half":[v-45 for v in durations]}


def run(root):
    root=Path(root).resolve(strict=True)
    manifest=json.loads(load(root,"manifest.json",100000).decode(),
                        object_pairs_hook=unique_object,parse_constant=reject_constant)
    if type(manifest) is not dict or set(manifest)!={"schema","rights_confirmed","event_blob_pins"} or manifest["schema"]!="statsbomb-private-wc2022-v1" or manifest["rights_confirmed"] is not True:
        raise ValueError("MANIFEST")
    rows=index(load(root,"matches.json",2000000))
    pins=manifest["event_blob_pins"]
    if type(pins) is not dict or set(pins)!={str(r[1]) for r in rows}:
        raise ValueError("COHORT_MANIFEST_SCOPE")
    if any(type(p) is not str or len(p)!=40 or any(c not in "0123456789abcdef" for c in p) for p in pins.values()):
        raise ValueError("EVENT_PIN")
    accepted=[];rejected=[]
    for _,mid,h,a in rows:
        try:
            result=inspect(load(root,f"{mid}.json",MAX),pins[str(mid)],h,a)
            accepted.append({"match_id":mid,**result})
        except (ValueError,KeyError,TypeError,AttributeError,OverflowError,OSError,RecursionError):
            rejected.append(mid)
    return {"source":"StatsBomb","index_pin":INDEX_PIN,"scheduled":len(rows),
            "accepted":len(accepted),"rejected_match_ids":rejected,"private_match_research":accepted,
            "red_card_matches":sum(r["regulation_cards"]>0 for r in accepted),
            "complete_cohort":len(accepted)==len(rows),"selection_bias_not_ruled_out":True,
            "announced_added_time_observed":False,"psxg_calibrated":False,
            "red_card_effect_calibrated":False,"model_calibrated":False,
            "source_authenticated":False,"verified_forward_sample_credit":0,
            "positive_ev_verified":False,"production_recommendations":"DISABLED","status":"HOLD"}


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_directory",type=Path)
    args=p.parse_args()
    print(json.dumps(run(args.private_directory),sort_keys=True,allow_nan=False))
