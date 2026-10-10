"""Hypothetical Asian handicap and totals diagnostics for uncalibrated six-league Shadow forecasts.

NEVER describe hypothetical lines as offered odds or as sportsbook recommendations.
No odds fetched, no EV, no staking, no automatic bet releases.
"""
import argparse
import html
import json
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path

from ops.asian_handicap_research import probabilities as ah_probs, _poisson, split_lines

SCHEMA = "football-king-six-league-market-scenario-research-v1"
LEAGUES = frozenset(("epl", "championship", "bundesliga", "laliga", "seriea", "ligue1"))
OUTCOMES = ("FULL_WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "FULL_LOSS")

def _utc(s):
    if not isinstance(s, str):
        raise ValueError("MISSING_UTC")
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("NAIVE_UTC")
    return d.astimezone(timezone.utc)

def _price(probs):
    win = probs["FULL_WIN"] + probs["HALF_WIN"]/2
    loss = probs["FULL_LOSS"] + probs["HALF_LOSS"]/2
    return round(1 + loss/win, 5) if win > 1e-8 else None

def total_scenario(home_rate, away_rate, *, side, line):
    if side not in ("OVER", "UNDER"):
        raise ValueError("INVALID_TOTAL_SIDE")
    left, right = split_lines(line)
    h, a = _poisson(home_rate), _poisson(away_rate)
    dist = {k: 0.0 for k in OUTCOMES}
    for home_goals, ph in enumerate(h):
        for away_goals, pa in enumerate(a):
            goals = home_goals + away_goals
            leg1 = (goals*4-left) * (1 if side == "OVER" else -1)
            leg2 = (goals*4-right) * (1 if side == "OVER" else -1)
            settle = sum(1 if v > 0 else -1 if v < 0 else 0 for v in (leg1,leg2))
            dist[dict(zip((2,1,0,-1,-2),OUTCOMES))[settle]] += ph*pa
    if abs(sum(dist.values())-1)>1e-8:
        raise ValueError("INVALID_TOTAL_DISTRIBUTION")
    return {
        "market": "totals", "side": side, "hypothetical_line": float(line),
        "settlement_probabilities": {k: round(dist[k],7) for k in OUTCOMES},
        "model_implied_neutral_decimal_price_not_a_quote": _price(dist),
        "actual_bookmaker_quote_available": False,
        "positive_expected_value_verified": False,
        "qualifies_for_betting": False,
    }

def ah_scenario(home_rate,away_rate,side,line):
    x = ah_probs(home_rate,away_rate,side,line)
    return {
        "market": "asian_handicap", "side": side,
        "hypothetical_line": float(line),
        "settlement_probabilities": x["outcome_probabilities"],
        "model_implied_neutral_decimal_price_not_a_quote":
            x["model_implied_neutral_decimal_price_not_a_quote"],
        "actual_bookmaker_quote_available": False,
        "positive_expected_value_verified": False,
        "qualifies_for_betting": False,
    }

def build(shadow,now=None,limit=8):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    empty = {
        "schema": SCHEMA, "generated_utc": now.isoformat(),
        "status": "HOLD", "research_only": True, "matches": [],
        "market_quotes_observed": False, "hypothetical_lines_only": True,
        "model_calibrated": False, "independent_forward_value_verified": False,
        "production_recommendations": "DISABLED", "recommended_bets": [],
        "notice": "盤線僅係數學示例，冇實際莊家報價；未校準 Poisson 模型唔能證明正 EV。",
    }
    if (not isinstance(shadow,dict)
            or shadow.get("production_recommendations")!="DISABLED"
            or shadow.get("status")!="SHADOW_ONLY"
            or shadow.get("model_calibrated") is not False
            or not isinstance(shadow.get("predictions"),list)
            or len(shadow["predictions"])>3000):
        return empty
    try:
        asof=_utc(shadow["as_of_utc"])
    except (KeyError,TypeError,ValueError,OverflowError):
        return empty
    if not timedelta(minutes=-5)<=now-asof<=timedelta(hours=10):
        return empty
    results,seen=[],set()
    for item in shadow["predictions"]:
        if not isinstance(item,dict):
            continue
        try:
            if item.get("production_recommendations")!="DISABLED" or item.get("calibrated") is not False:
                continue
            if item.get("league") not in LEAGUES:
                continue
            home,away=item["home"],item["away"]
            if (not all(isinstance(x,str) and 0<len(x)<=120 for x in (home,away))
                    or home==away):
                continue
            kickoff=_utc(item["kickoff_utc"])
            forecast=_utc(item["prediction_utc"])
            if not (asof-timedelta(minutes=2)<=forecast<=asof+timedelta(minutes=2)
                    and forecast<kickoff
                    and now+timedelta(minutes=60)<kickoff<=now+timedelta(days=7)):
                continue
            hg,ag=item["expected_home_goals"],item["expected_away_goals"]
            if (type(hg) not in (int,float) or type(ag) not in (int,float)
                    or not all(math.isfinite(v) and 0.1<=v<=5.5 for v in (hg,ag))):
                continue
            key=(item["league"],home,away,kickoff.isoformat())
            if key in seen:
                continue
            seen.add(key)
            scenarios=[
                ah_scenario(hg,ag,"HOME",-0.25),
                ah_scenario(hg,ag,"AWAY",0.25),
                total_scenario(hg,ag,side="OVER",line=2.5),
                total_scenario(hg,ag,side="UNDER",line=2.5),
            ]
            results.append({
                "league": item["league"], "home": home, "away": away,
                "kickoff_utc": kickoff.isoformat(),
                "prediction_utc": forecast.isoformat(),
                "expected_home_goals": round(hg,5),
                "expected_away_goals": round(ag,5),
                "scenarios": scenarios,
                "real_odds": None, "suggested_stake": None,
                "production_recommendations": "DISABLED",
            })
        except (KeyError,TypeError,ValueError,OverflowError,AttributeError):
            continue
    results.sort(key=lambda x:(x["kickoff_utc"],x["league"],x["home"]))
    return {**empty,"status":"RESEARCH_ONLY" if results else "HOLD",
            "matches": results[:limit]}

def render(report):
    if report["production_recommendations"]!="DISABLED":
        raise ValueError("UNSAFE_MARKET_RESEARCH")
    esc=html.escape
    parts=[
        '<section id="fk-all-market-hypotheses" role="region">',
        '<h2>亞洲讓球／大小球模型假設研究</h2>',
        '<p class="small">所有盤線僅屬示例，不代表目前莊家有開盤；'
        '中性價係未校準 Poisson 模型計數結果，並非投注建議、勝率認證或正EV證據。</p>',
    ]
    if not report["matches"]:
        parts.append('<p>暫無通過賽前時間及數據完整性檢查嘅假設情景。</p>')
    else:
        for match in report["matches"]:
            parts.append('<div class="fk-market-hypothesis">')
            parts.append('<h3>'+esc(match["home"])+' — '+esc(match["away"])+'</h3>')
            parts.append('<p class="small">模型預期入球：主 '+str(match["expected_home_goals"])
                         +' ／ 客 '+str(match["expected_away_goals"])+'</p>')
            pieces=[]
            for s in match["scenarios"]:
                label = ("主讓0.25" if s["market"]=="asian_handicap" and s["side"]=="HOME"
                         else "客受讓0.25" if s["market"]=="asian_handicap"
                         else "大2.5" if s["side"]=="OVER" else "細2.5")
                neutral=s["model_implied_neutral_decimal_price_not_a_quote"]
                pieces.append(esc(label)+": 模型中性價 "+(str(neutral) if neutral else "不可計算"))
            parts.append('<p class="small">'+esc("；".join(pieces))+'</p>')
            parts.append('</div>')
    parts.append('<p><a href="all_market_scenarios.json">查看完整五級結算分布（研究用途）</a></p>')
    parts.append('</section>')
    return "".join(parts)

def publish(site,now=None):
    site=Path(site)
    source=json.loads((site/"shadow.json").read_text(encoding="utf-8"))
    report=build(source,now)
    page=site/"index.html"
    markup=page.read_text(encoding="utf-8")
    if 'id="fk-all-market-hypotheses"' in markup:
        raise ValueError("DUPLICATE_MARKET_HYPOTHESIS")
    anchor="<h2>近期賽程與賽果</h2>"
    if anchor in markup:
        markup=markup.replace(anchor,render(report)+anchor,1)
    elif "</main>" in markup:
        markup=markup.replace("</main>",render(report)+"</main>",1)
    else:
        raise ValueError("MISSING_SAFE_INSERTION_POINT")
    (site/"all_market_scenarios.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    page.write_text(markup,encoding="utf-8")
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--site",default="app/site")
    a=p.parse_args()
    r=publish(a.site)
    print("ALL_MARKET_HYPOTHETICAL:",r["status"],"CASES:",len(r["matches"]),
          "PRODUCTION_RECOMMENDATIONS:",r["production_recommendations"])
