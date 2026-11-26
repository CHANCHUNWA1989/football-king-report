"""V30 authorized player-history lineup residual against V10.1.
No live data or invented player ratings. Local clocks and rights are declarations.
"""
import argparse,json,math
from collections import defaultdict
from datetime import datetime,timezone,timedelta,date
from pathlib import Path
from zoneinfo import ZoneInfo
from ops import v9_lineup_research as xi,v9_stacking_research as s
from ops import v5_ensemble_competition as e,v8_multiseason as v
from ops.v29_xg_residual import checked,read,enc,ZONES
from ops.v6_forward_bundle import decode,utc
from ops.v20_signed_receipts import bounded,sha
from ops.v5_ucl_source_gate import ident
from ops.v9_league_weights import ci

GRID=(0.,.25,.5,1.,2.)
HALF_LIFE=180.
SHRINK_MINUTES=450.
MIN_MINUTES=180
MIN_MATCHES=3
MAX_HISTORY=100000

def history(raw,expected,provider,league,now):
    d=checked(raw,expected)
    if d.get("schema")!="v30-player-history-v1" or d.get("provider")!=provider or d.get("league")!=league or d.get("rating_definition")!="PROVIDER_NORMALIZED_SIGNED_CONTRIBUTION_V1":
        raise ValueError("PLAYER_HISTORY_SCOPE")
    captured=utc(d["captured_utc"])
    if captured>now or not isinstance(d["rows"],list) or not 1<=len(d["rows"])<=MAX_HISTORY:raise ValueError("PLAYER_HISTORY_CAPTURE")
    seen=set();groups=defaultdict(list);matches={}
    for r in d["rows"]:
        if set(r)!={"match_id","team_id","player_id","kickoff_utc","available_utc","minutes","rating"}:raise ValueError("PLAYER_FIELDS")
        mid,team,pid=map(ident,(r["match_id"],r["team_id"],r["player_id"]))
        ko,av=map(utc,(r["kickoff_utc"],r["available_utc"]))
        key=(mid,pid)
        if key in seen or not ko+timedelta(hours=2)<=av<=captured:raise ValueError("PLAYER_CLOCK_OR_DUPLICATE")
        prior=matches.setdefault(mid,(ko,set()))
        if prior[0]!=ko:raise ValueError("PLAYER_MATCH_CLOCK")
        prior[1].add(team)
        if len(prior[1])>2:raise ValueError("PLAYER_MATCH_TEAMS")
        minutes,rating=r["minutes"],r["rating"]
        if type(minutes) is not int or not 1<=minutes<=90 or type(rating) not in (int,float) or not math.isfinite(rating) or not -1<=rating<=1:raise ValueError("PLAYER_RATING")
        seen.add(key);groups[(team,pid)].append((mid,ko,av,minutes,rating))
    return groups

def estimate(rows,cut,target_id):
    prior=[r for r in rows if r[0]!=target_id and r[1].date()<cut.date() and r[2]<cut]
    if len(prior)<MIN_MATCHES or sum(r[3] for r in prior)<MIN_MINUTES:return None
    weights=[r[3]*2**(-(cut-r[1]).total_seconds()/86400/HALF_LIFE) for r in prior]
    return math.fsum(w*r[4] for w,r in zip(weights,prior))/(SHRINK_MINUTES+math.fsum(weights)),max(r[2] for r in prior)

def derive(side,groups,target):
    team=ident(side["team_id"]);cut=utc(side["expected_xi_utc"])
    players=xi.players(side["expected_xi"])|xi.players(side["confirmed_xi"])
    ratings=[]
    for pid in sorted(players):
        q=estimate(groups.get((team,pid),[]),cut,target)
        if q is None:return None
        ratings.append({"player_id":pid,"team_id":team,"rating":q[0],"available_utc":q[1].isoformat()})
    return {**side,"ratings":ratings}

def pair(anchor,raw,meta,mapping,groups,now):
    if anchor.get("schema")!="v29-stack-reference-v1" or anchor.get("historical_source_commit")!=v.PIN or anchor.get("status")!="HOLD" or anchor.get("production_recommendations")!="DISABLED" or anchor.get("verified_forward_sample_credit")!=0:raise ValueError("ANCHOR_CONTRACT")
    league=meta["competition_scope"];provider=meta["provider"]
    if mapping.get("schema")!="v30-lineup-fixture-crosswalk-v1" or mapping.get("league")!=league or mapping.get("provider")!=provider:raise ValueError("MAP_SCOPE")
    # Validate the original lineup capture before deriving replacement ratings.
    original=xi.load(raw,meta,now);doc=decode(raw)
    byid={ident(r["match_id"]):r for r in doc["matches"]}
    orig={r["id"]:r for r in original}
    idx={}
    for r in anchor["rows"]:
        if r["league"]!=league:continue
        key=e.key(r)
        if key in idx or r["season"] not in (s.CAL,s.TEST):raise ValueError("ANCHOR_ID")
        year=int(r["season"][:4])
        if not date(year,7,1)<=date.fromisoformat(r["date"])<date(year+1,7,1):raise ValueError("ANCHOR_DATE")
        e.vec(r["stack"]);idx[key]=r
    seen=set();keys=set();derived=[];links={};missing=0
    for m in mapping["pairs"]:
        if set(m)!={"match_id","home_id","away_id","kickoff_utc","date","home","away","evidence_reference"}:raise ValueError("MAP_FIELDS")
        mid=ident(m["match_id"]);key=e.key(m);r=byid.get(mid);a=idx.get(key)
        if mid in seen or key in keys or r is None or a is None or not isinstance(m["evidence_reference"],str) or not m["evidence_reference"].startswith("https://"):raise ValueError("MAP_ID")
        seen.add(mid);keys.add(key)
        ko=utc(r["kickoff_utc"])
        if (ident(r["home"]["team_id"]),ident(r["away"]["team_id"]),ko)!=(ident(m["home_id"]),ident(m["away_id"]),utc(m["kickoff_utc"])) or ko.astimezone(ZoneInfo(ZONES[league])).date().isoformat()!=m["date"] or a["goals"]!=[r["home_goals"],r["away_goals"]] or a["y"]!=orig[mid]["y"]:raise ValueError("MAP_SCORE_CLOCK")
        if max(abs(x-y) for x,y in zip(e.vec(a["stack"]),orig[mid]["baseline"]))>1e-8:raise ValueError("ANCHOR_PROBABILITY_MISMATCH")
        h=derive(r["home"],groups,mid);b=derive(r["away"],groups,mid)
        if h is None or b is None:missing+=1;continue
        derived.append({**r,"home":h,"away":b});links[mid]=a
    if not derived:return [],len(idx),missing
    # Internal transformation only; retain original input digests in result.
    converted=enc({**doc,"matches":derived})
    clean=xi.load(converted,{**meta,"sha256":sha(converted)},now)
    return [{**links[r["id"]],**{k:r[k] for k in ("id","ko","available","rating_delta","changes")}} for r in clean],len(idx),missing

def adjust(r,b):
    if b not in GRID:raise ValueError("LINEUP_PARAMETER")
    p=e.vec(r["stack"]);d=r["rating_delta"]
    if type(d) not in (int,float) or not math.isfinite(d) or abs(d)>4:raise ValueError("RATING_DELTA")
    if b==0 or d==0:return p
    z=max(-.5,min(.5,b*d))
    q=[p[0]*math.exp(z),p[1],p[2]*math.exp(-z)]
    return e.vec([x/math.fsum(q) for x in q])

def evaluate(rows,total,missing):
    split=utc("2025-07-01T00:00:00Z");end=utc("2026-07-01T00:00:00Z")
    cal=[r for r in rows if r["season"]==s.CAL and r["ko"]<split and r["available"]<split]
    test=[r for r in rows if r["season"]==s.TEST and split<=r["ko"]<end and r["available"]<end]
    out={"schema":"v30-player-lineup-residual-research-v1","reference_n":total,"missing_player_history":missing,
         "calibration_n":len(cal),"assessment_n":len(test),"selected_coefficient":None,"metrics":None,
         "verified_forward_sample_credit":0,"automatic_promotion":False,"production_recommendations":"DISABLED","status":"HOLD",
         "actual_source_and_clock_authenticated":False,"assessment_previously_inspected":True}
    if len(cal)<100 or len(test)<50 or {r["y"] for r in cal}!={0,1,2} or {r["y"] for r in test}!={0,1,2} or sum(r["changes"]>0 for r in cal)<50 or sum(r["changes"]>0 for r in test)<25:
        return {**out,"reason":"INSUFFICIENT_PAIRED_LINEUP_COHORT"}
    b=min(GRID,key=lambda b:(math.fsum(e.loss(adjust(r,b),r["y"]) for r in cal)/len(cal)+.002*b*b,b))
    scored=[{**r,"hybrid":r["stack"],"candidate":adjust(r,b)} for r in test]
    def metrics(a):return {k:e.metrics(a,lambda r:r[k]) for k in ("stack","candidate")}
    m=metrics(scored);interval=ci(scored)
    return {**out,"selected_coefficient":b,"metrics":m,"changed_xi_metrics":metrics([r for r in scored if r["changes"]]),
         "paired_week_ci_stack_minus_candidate":interval,
         "historical_proper_score_gate":bool(b and interval and interval[0]>0 and all(m["candidate"][k]<m["stack"][k] for k in ("log_loss","brier")))}

def run(anchor_raw,anchor_sha,raw,meta_raw,map_raw,map_sha,history_raw,history_sha,*,now):
    meta=decode(bounded(meta_raw,100000))
    if meta.get("competition_scope") not in ZONES or meta.get("owner_authorization_reviewed") is not True or meta.get("historical_availability_recorded") is not True or meta.get("player_history_authorization_reviewed") is not True:
        raise ValueError("AUTHORIZATION_OR_AVAILABILITY_REQUIRED")
    a=checked(anchor_raw,anchor_sha);m=checked(map_raw,map_sha)
    groups=history(history_raw,history_sha,meta["provider"],meta["competition_scope"],now)
    rows,total,missing=pair(a,raw,meta,m,groups,now)
    return {**evaluate(rows,total,missing),"league":meta["competition_scope"],"input_sha256":[sha(x) for x in (anchor_raw,raw,meta_raw,map_raw,history_raw)]}
def main():
    p=argparse.ArgumentParser()
    for k in ("anchor","anchor-sha256","capture","metadata","mapping","mapping-sha256","player-history","player-history-sha256","output"):p.add_argument("--"+k,required=True)
    a=p.parse_args();out=run(read(a.anchor),a.anchor_sha256,read(a.capture),read(a.metadata),read(a.mapping),a.mapping_sha256,read(a.player_history),a.player_history_sha256,now=datetime.now(timezone.utc))
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
