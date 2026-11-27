"""V9.3 authorized prematch player-availability research, no live qualification."""
import argparse,hashlib,json,math
from pathlib import Path
from datetime import datetime,timedelta,timezone
from ops.v6_forward_bundle import decode
from ops.v5_ucl_source_gate import utc,ident
from ops.v5_ensemble_competition import vec,metrics

MAX_BYTES=4_000_000
def sha(raw):return hashlib.sha256(raw).hexdigest()
def clock(s,cut):
    d=utc(s)
    if d>cut:raise ValueError("AFTER_FORECAST")
    return d
def probability(p):
    if not isinstance(p,list) or len(p)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in p) or abs(sum(p)-1)>0.00001:raise ValueError("INVALID_PROBABILITY")
    return vec(p)
def players(values):
    if not isinstance(values,list) or len(values)!=11:raise ValueError("INVALID_XI")
    ids=[ident(x) for x in values]
    if len(set(ids))!=11:raise ValueError("DUPLICATE_PLAYER")
    return set(ids)
def side(s,forecast,kickoff):
    team=ident(s["team_id"])
    published=clock(s["lineup_published_utc"],forecast)
    captured=clock(s["lineup_captured_utc"],forecast)
    expected_at=clock(s["expected_xi_utc"],forecast)
    if not kickoff-timedelta(hours=3)<=published<=captured or expected_at>=published:raise ValueError("LINEUP_CHRONOLOGY")
    if s["lineup_status"]!="CONFIRMED":raise ValueError("UNCONFIRMED_XI")
    expected=players(s["expected_xi"]);actual=players(s["confirmed_xi"])
    ratings=s["ratings"]
    if not isinstance(ratings,list) or len(ratings)>60:raise ValueError("RATING_SCOPE")
    scores={}
    for r in ratings:
        pid=ident(r["player_id"])
        if pid in scores or ident(r["team_id"])!=team:raise ValueError("RATING_IDENTITY")
        # Ratings must be available before expected-XI capture, not updated after lineup.
        clock(r["available_utc"],expected_at)
        v=r["rating"]
        if type(v) not in (int,float) or not math.isfinite(v) or not -1<=v<=1:raise ValueError("RATING_SCALE")
        scores[pid]=v
    if not expected|actual<=scores.keys():raise ValueError("MISSING_PLAYER_RATING")
    absences=s["absences"]
    if not isinstance(absences,list) or len(absences)>60:raise ValueError("ABSENCE_SCOPE")
    unavailable=set()
    for r in absences:
        pid=ident(r["player_id"])
        if ident(r["team_id"])!=team or pid in unavailable:raise ValueError("ABSENCE_IDENTITY")
        clock(r["reported_utc"],forecast)
        if r["status"] not in ("CONFIRMED_UNAVAILABLE","SUSPENDED"):raise ValueError("UNCONFIRMED_ABSENCE")
        unavailable.add(pid)
    if actual&unavailable:raise ValueError("XI_ABSENCE_CONFLICT")
    # Absences only validate the lineup, never add a second penalty.
    change=(sum(scores[p] for p in actual)-sum(scores[p] for p in expected))/11
    return team,expected|actual,change,len(expected-actual)
def adjust(p,d):
    p=probability(p)
    if not math.isfinite(d) or not -4<=d<=4:raise ValueError("BAD_DELTA")
    # Fixed bounded research perturbation, not a fitted player-value model.
    shift=max(-.25,min(.25,d*.5))
    vals=[p[0]*math.exp(shift),p[1],p[2]*math.exp(-shift)]
    return vec([v/sum(vals) for v in vals])
def load(raw,meta,now):
    if not 0<len(raw)<=MAX_BYTES or meta.get("schema")!="v9-3-authorized-lineup-receipt-v1" or meta.get("sha256")!=sha(raw):raise ValueError("INTEGRITY")
    for k in ("provider","authorization_reference","rating_definition"):
        if not isinstance(meta.get(k),str) or not meta[k].strip():raise ValueError("METADATA")
    captured=clock(meta["captured_utc"],now)
    doc=decode(raw)
    if doc.get("schema")!="v9-3-lineup-research-cases-v1" or doc.get("provider")!=meta["provider"] or doc.get("rating_definition")!=meta["rating_definition"]:raise ValueError("SCOPE")
    rows=doc["matches"]
    if not isinstance(rows,list) or not 1<=len(rows)<=10000:raise ValueError("ROW_COUNT")
    seen=set();pairs=set();out=[]
    for r in rows:
        mid=ident(r["match_id"]);ko=utc(r["kickoff_utc"]);f=clock(r["forecast_utc"],captured)
        if not f<ko or ko+timedelta(hours=2)>captured or r["phase"]!="REGULATION" or r["status"]!="FINISHED":raise ValueError("MATCH_CLOCK")
        clock(r["result_available_utc"],captured)
        if utc(r["result_available_utc"])<ko+timedelta(hours=2):raise ValueError("RESULT_CLOCK")
        h,hp,hd,hc=side(r["home"],f,ko);a,ap,ad,ac=side(r["away"],f,ko)
        if h==a or hp&ap or mid in seen or (ko,h,a) in pairs:raise ValueError("FIXTURE_IDENTITY")
        seen.add(mid);pairs.add((ko,h,a))
        x,y=r["home_goals"],r["away_goals"]
        if any(type(v) is not int or not 0<=v<=20 for v in (x,y)):raise ValueError("SCORE")
        p=probability(r["baseline_probability"])
        if r.get("baseline_conditioned_on_confirmed_xi") is not False:raise ValueError("BASELINE_SCOPE")
        out.append({"date":ko.date().isoformat(),"y":0 if x>y else 1 if x==y else 2,"baseline":p,"candidate":adjust(p,hd-ad),"changes":hc+ac,"id":mid,"ko":ko,"available":utc(r["result_available_utc"]),"rating_delta":hd-ad})
    return out
def build(rows):
    changed=[r for r in rows if r["changes"]]
    return {"schema":"v9-3-lineup-research-v1","paired_matches":len(rows),"changed_xi_matches":len(changed),
        "all_same_fixture":{"baseline":metrics(rows,lambda r:r["baseline"]),"candidate":metrics(rows,lambda r:r["candidate"])},
        "changed_same_fixture":{"baseline":metrics(changed,lambda r:r["baseline"]),"candidate":metrics(changed,lambda r:r["candidate"])},
        "local_metadata_not_authenticated":True,"rating_effect_fitted":False,"baseline_lineup_exclusion_independently_verified":False,
        "official_lineup_authenticated":False,"verified_forward_sample_credit":0,"production_recommendations":"DISABLED","automatic_promotion":False,"status":"HOLD"}
def main():
    p=argparse.ArgumentParser()
    for k in ("capture","metadata","output"):p.add_argument("--"+k,required=True)
    a=p.parse_args();f=Path(a.capture);m=Path(a.metadata)
    if not 0<f.stat().st_size<=MAX_BYTES or not 0<m.stat().st_size<=100000:raise ValueError("SIZE")
    out=build(load(f.read_bytes(),decode(m.read_bytes()),datetime.now(timezone.utc)))
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
