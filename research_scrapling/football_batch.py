"""Bounded Bundesliga round-one historical comparison; no live eligibility."""
import json
from pathlib import Path
import historical_probe as p

# Explicit aliases only; unresolved names are not fuzzy-matched.
ALIASES={
40:("Bayern München","FC Bayern München","Bayern Munich","FC Bayern Munich"),
9:("Schalke 04","FC Schalke 04"),
91:("Eintracht Frankfurt",),83:("Arminia Bielefeld","DSC Arminia Bielefeld"),
65:("1. FC Köln","FC Köln","1. FC Cologne","FC Cologne"),
175:("TSG Hoffenheim","TSG 1899 Hoffenheim","1899 Hoffenheim"),
16:("VfB Stuttgart",),112:("SC Freiburg",),
80:("1. FC Union Berlin","Union Berlin"),95:("FC Augsburg",),
134:("Werder Bremen","SV Werder Bremen"),54:("Hertha BSC","Hertha Berlin"),
7:("Borussia Dortmund",),87:("Borussia Mönchengladbach",),
1635:("RB Leipzig",),81:("1. FSV Mainz 05","FSV Mainz 05","Mainz 05"),
}
EXPECTED={58577,58579,58580,58582,58584,58578,58581}

def compare(a,b):
    results=[]
    for mid in sorted(EXPECTED):
        row={"match_id":mid,"status":"HOLD"}
        try:
            xs=[x for x in a if x["matchID"]==mid]
            if len(xs)!=1:raise ValueError("missing or duplicate match")
            x=xs[0]
            if x["leagueShortcut"]!="bl1" or x["leagueSeason"]!=2020 or x["group"]["groupOrderID"]!=1 or x["matchIsFinished"] is not True:
                raise ValueError("wrong league, season, round or status")
            day=x["matchDateTime"][:10]
            home=ALIASES[x["team1"]["teamId"]];away=ALIASES[x["team2"]["teamId"]]
            ys=[y for y in b["matches"] if y["date"]==day and y["team1"] in home and y["team2"] in away]
            scores=[(s["pointsTeam1"],s["pointsTeam2"]) for s in x["matchResults"] if s["resultTypeID"]==2]
            if len(ys)!=1 or len(scores)!=1:raise ValueError("ambiguous match or score")
            other=ys[0]["score"]["ft"]
            row.update(date=day,home=x["team1"]["teamName"],away=x["team2"]["teamName"],
                       score_a=list(scores[0]),score_b=other,status=p.score_pair(scores[0],other))
        except (KeyError,TypeError,ValueError) as e:
            row["error_type"]=type(e).__name__
        results.append(row)
    return results

if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument("output",type=Path);args=ap.parse_args()
    r=dict(status="HOLD",historical_only=True,production_recommendations="DISABLED",
           independent_upstream_certified=False,source_evidence=[],rows=[])
    try:
        a,ea=p.acquire(p.OPENLIGA);b,eb=p.acquire(p.OPENFOOT)
        r["source_evidence"]=[ea,eb]
        r["rows"]=compare(json.loads(a),json.loads(b))
    except Exception as e:r["error_type"]=type(e).__name__
    r["matched"]=sum(x["status"]=="HISTORICAL_MATCH" for x in r["rows"])
    r["expected"]=len(EXPECTED)
    args.output.write_text(json.dumps(r,indent=2,ensure_ascii=False))
    if r["matched"]!=r["expected"]:raise SystemExit(2)
