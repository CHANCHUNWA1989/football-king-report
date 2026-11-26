"""Frozen cross-league retrospective replication of state_shrink50."""
import json
import math
from urllib.request import Request,build_opener
from live_core_multi_source import blob,checked,row,unique,NoRedirect,LIMIT
from research_strict_json import unique_object,reject_constant
from live_core_venue_bias_replay import SPECS,SEASONS
from live_core_deep_state_rates import report
from live_core_deep_halftime_replay import LINES

COVERAGE={"EPL":(357,369),"BL":(291,293),"ES":(354,349)}
DISTINCT=("-1.5","-2.0","-2.5","-3.0")

def parse(raw,league,season):
    if league not in SPECS or season not in SEASONS:raise ValueError("SOURCE_SCOPE")
    _,name,n,pins=SPECS[league];idx=SEASONS.index(season)
    if blob(raw)!=pins[idx]:raise ValueError("BLOB_PIN_CHANGED")
    d=json.loads(checked(raw),object_pairs_hook=unique_object,parse_constant=reject_constant)
    if d["name"]!=name+" "+season.replace("-","/") or len(d["matches"])!=n:raise ValueError("LEAGUE_SCOPE")
    all_rows=[];out=[];year=int(season[:4])
    for m in d["matches"]:
        day,h,a,x,y=row(m["date"],m["team1"],m["team2"],m["score"]["ft"])
        if not f"{year}-07-01"<=day<f"{year+1}-07-01":raise ValueError("DATE_SCOPE")
        all_rows.append((day,h,a,x,y))
        ht=m["score"].get("ht")
        if ht is None:continue
        _,_,_,i,j=row(day,h,a,ht)
        if i>x or j>y:raise ValueError("HALFTIME_SCORE")
        out.append((day,h,a,i,j,x,y))
    unique(all_rows)
    if len(out)!=COVERAGE[league][idx]:raise ValueError("COVERAGE")
    return sorted(out)

def fetch(league,season):
    url=f"https://raw.githubusercontent.com/openfootball/football.json/master/{season}/{SPECS[league][0]}.json"
    with build_opener(NoRedirect()).open(Request(url,headers={"User-Agent":"FootballKingResearch/1.0","Accept":"application/json"}),timeout=15) as res:
        if res.geturl()!=url or res.status!=200:raise ValueError("HTTP_SOURCE")
        raw=res.read(LIMIT+1)
    return parse(raw,league,season)

def summarize(reports):
    if set(reports)!=set(SPECS):raise ValueError("LEAGUE_SCOPE")
    counts={"both_improve":0,"both_worse":0,"mixed_or_equal":0,"unavailable":0}
    n=0;train=0;test=0
    for league,r in reports.items():
        if (r["train_n"],r["assessment_n"])!=COVERAGE[league]:raise ValueError("COVERAGE")
        k=r["eligible_n"]
        if type(k) is not int or not 0<=k<=r["assessment_n"] or k+r["excluded_n"]!=r["assessment_n"]:
            raise ValueError("DENOMINATOR")
        if r["verified_forward_sample_credit"]!=0 or r["production_recommendations"]!="DISABLED":raise ValueError("UNSAFE_REPORT")
        if sum(r["assessment_group_counts"].values())!=k:raise ValueError("GROUP_COUNT")
        n+=k;train+=r["train_n"];test+=r["assessment_n"]
        for line in DISTINCT:
            d=r["by_hypothetical_line"][line]
            if d["n"]!=k or sum(d["grades"].values())!=k:raise ValueError("LINE_COUNT")
            b,l=(d["state_minus_baseline"][v] for v in ("brier","log_loss"))
            if not k:
                if b is not None or l is not None:raise ValueError("EMPTY_METRIC")
                counts["unavailable"]+=1;continue
            if any(type(x) not in (float,int) or not math.isfinite(x) for x in (b,l)):raise ValueError("METRIC")
            counts["both_improve" if b<0 and l<0 else "both_worse" if b>0 and l>0 else "mixed_or_equal"]+=1
    return {"schema":"football-king-deep-cross-league-v1","leagues":reports,
            "train_n":train,"assessment_n":test,"eligible_n":n,
            "distinct_league_line_comparisons":12,"direction_counts":counts,
            "train_season":SEASONS[0],"assessment_season":SEASONS[1],
            "fixed_protocol":"state_shrink50","retrospective_replication_only":True,
            "no_pooled_inference":True,"actual_market_lines_verified":False,
            "independent_prospective_validation":False,"verified_forward_sample_credit":0,
            "positive_ev_verified":False,"production_recommendations":"DISABLED","status":"HOLD"}

def run():
    return summarize({k:report(fetch(k,SEASONS[0]),fetch(k,SEASONS[1])) for k in SPECS})

if __name__=="__main__":print(json.dumps(run(),sort_keys=True,allow_nan=False))
