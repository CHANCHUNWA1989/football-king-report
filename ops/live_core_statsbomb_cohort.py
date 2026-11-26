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

from live_core_statsbomb_wc2022_pins import UPSTREAM_COMMIT, UPSTREAM_TREE, INDEX_BLOB, EVENT_BLOBS

INDEX_PIN=INDEX_BLOB
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
    context={k:out[k] for k in ("single_dismissal_event","score_immediately_before_dismissal") if k in out}
    return {**context,"home_id":h,"away_id":a,"actual_on_pitch_verified":False,
            "buckets":out["buckets"],"regulation_cards":out["regulation_cards"],
            "elapsed_minutes_by_half":durations,
            "elapsed_beyond_45_by_half":[v-45 for v in durations]}


def temporal_summary(planned, accepted):
    """Fixed date split; exposure-weighted descriptive rates, not causal coefficients."""
    out={}
    for label,select in (("group_stage",lambda day:day<"2022-12-03"),
                         ("knockout_stage",lambda day:day>="2022-12-03")):
        expected=sum(select(r[0]) for r in planned)
        chosen=[r for r in accepted if select(r["match_date"])]
        state=defaultdict(lambda:{"minutes":0.0,"xg":[0.0,0.0],"shots":[0,0],"matches":0})
        for row in chosen:
            for b in row["buckets"]:
                key=tuple(b["dismissals"])
                cell=state[key];cell["minutes"]+=b["elapsed_minutes"];cell["matches"]+=1
                for i in (0,1):
                    cell["xg"][i]+=b["xg"][i];cell["shots"][i]+=b["shots"][i]
        cells=[]
        for key,v in sorted(state.items()):
            cells.append({"dismissals":list(key),**v,
                          "xg_per_90":[90*x/v["minutes"] for x in v["xg"]] if v["minutes"]>0 else None,
                          "small_sample":v["matches"]<10})
        out[label]={"scheduled":expected,"accepted":len(chosen),"rejected":expected-len(chosen),
                    "red_card_matches":sum(r["regulation_cards"]>0 for r in chosen),
                    "mean_elapsed_beyond_45_by_half":[sum(r["elapsed_beyond_45_by_half"][i] for r in chosen)/len(chosen) for i in (0,1)] if chosen else None,
                    "state_exposure":cells}
    return {"splits":out,"descriptive_only":True,"causal_effect_estimated":False,
            "independent_validation":False,"model_calibrated":False}


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
    if set(pins)!=set(EVENT_BLOBS) or any(pins[mid]!=EVENT_BLOBS[mid][0] for mid in pins):
        raise ValueError("UNPINNED_EVENT_REVISION")
    accepted=[];rejected=[]
    rejection_counts=defaultdict(int)
    for day,mid,h,a in rows:
        try:
            raw=load(root,f"{mid}.json",MAX)
            if len(raw)!=EVENT_BLOBS[str(mid)][1]:
                raise ValueError("EVENT_BYTE_LENGTH")
            result=inspect(raw,pins[str(mid)],h,a)
            accepted.append({"match_id":mid,"match_date":day,**result})
        except (ValueError,KeyError,TypeError,AttributeError,OverflowError,OSError,RecursionError) as exc:
            rejected.append(mid)
            allowed={"PRIVATE_FILE","SIZE","EVENT_BYTE_LENGTH","BLOB_MISMATCH","EVENT_ORDER",
                     "EVENT_TIME_REGRESSION","NON_ROSTER_RED_REVIEW","MISSING_OR_INVALID_XG",
                     "PERIOD_END","SHORT_PERIOD","INCOMPLETE_REGULATION","SUBSTITUTION","STARTING_XI",
                     "NONREGULATION_BEFORE_REGULATION_END","REGULATION_AFTER_NONREGULATION"}
            reason=str(exc) if isinstance(exc,ValueError) and str(exc) in allowed else "OTHER_REPLAY_REJECTION"
            rejection_counts[reason]+=1
    return {"source":"StatsBomb","index_pin":INDEX_PIN,"upstream_commit_pin":UPSTREAM_COMMIT,"upstream_tree_pin":UPSTREAM_TREE,
            "event_revisions_pinned":len(EVENT_BLOBS),"rejection_counts":dict(sorted(rejection_counts.items())),
            "scheduled":len(rows),
            "accepted":len(accepted),"rejected_match_ids":rejected,"private_match_research":accepted,
            "red_card_matches":sum(r["regulation_cards"]>0 for r in accepted),
            "complete_cohort":len(accepted)==len(rows),"selection_bias_not_ruled_out":True,
            "private_temporal_descriptives":temporal_summary(rows,accepted),
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
