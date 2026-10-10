"""Publish EVERY qualified time-safe 1X2 research direction for later verification.

The normal eight-pick editorial shortlist remains unchanged. This wider cohort
also includes threshold or model/market disagreements; hiding misses would bias
evaluation. Raw bookmaker quotes, actionable odds and stakes are prohibited.
Each displayed event is drawn from the same point-in-time paired-model audit
and is separately archived by GitHub workflow run ID.
"""
import argparse
import csv
import hashlib
import html
import io
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from research_recommender import build as shortlist_build, timestamp

HK = ZoneInfo("Asia/Hong_Kong")
MAX_VERIFICATION_ROWS = 100
DIRECTIONS = {"HOME": "主勝", "DRAW": "和局", "AWAY": "客勝"}
LEAGUES = ("epl", "championship", "bundesliga", "laliga", "seriea", "ligue1")
LEAGUE_NAMES = {"epl":"英超", "championship":"英冠", "bundesliga":"德甲",
                "laliga":"西甲", "seriea":"意甲", "ligue1":"法甲"}

def _make_row(item, grade):
    if (not isinstance(item, dict)
            or item.get("production_recommendations") != "DISABLED"
            or item.get("executable_market_odds_available") is not False
            or item.get("value_bet_verified") is not False
            or item.get("qualifies_for_value_recommendation") is not False
            or item.get("suggested_stake") is not None
            or item.get("reliability") != "UNCALIBRATED_RESEARCH_ONLY"
            or grade not in ("A_RESEARCH", "B_VERIFICATION_ONLY")
            or item.get("league") not in LEAGUES
            or item.get("direction") not in DIRECTIONS):
        raise ValueError("UNSAFE_VERIFICATION_ENTRY")
    kickoff = timestamp(item["kickoff_utc"])
    prediction = timestamp(item["prediction_utc"])
    market_stamp = timestamp(item["market_snapshot_utc"])
    updated = timestamp(item["market_updated_utc"])
    if not updated <= market_stamp <= prediction < kickoff:
        raise ValueError("UNSAFE_MARKET_CHRONOLOGY")
    model, consensus = item["model_probability_1x2"], item["market_consensus_1x2"]
    if (len(model) != 3 or len(consensus) != 3
            or any(type(v) not in (int, float) for v in model+consensus)
            or abs(sum(model)-1) > .002 or abs(sum(consensus)-1) > .002):
        raise ValueError("UNSAFE_PROBABILITY_VECTOR")
    uid = item["case_id"]
    if not isinstance(uid, str) or len(uid) != 64 or any(x not in "0123456789abcdef" for x in uid):
        # Older fixture identity formats can use shorter stable IDs; protect with
        # the existing unique string, but the export uses its hashed reference.
        if not isinstance(uid, str) or not uid or len(uid) > 160:
            raise ValueError("INVALID_PAIR_CASE_ID")
    anchor = hashlib.sha256(json.dumps([
        uid, item["league"], item["home"], item["away"],
        kickoff.isoformat(), prediction.isoformat(), model, consensus],
        ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    probability = item["research_probability"]
    if (type(probability) not in (int, float)
            or not 0 <= probability <= 1):
        raise ValueError("BAD_SELECTED_PROBABILITY")
    return {
        "sealed_pick_digest": anchor,
        "case_id": uid,
        "league": item["league"], "home": item["home"], "away": item["away"],
        "kickoff_utc": kickoff.isoformat(),
        "kickoff_hong_kong": kickoff.astimezone(HK).strftime("%Y-%m-%d %H:%M"),
        "prediction_utc": prediction.isoformat(),
        "market_snapshot_utc": market_stamp.isoformat(),
        "market_updated_utc": updated.isoformat(),
        "research_tier": grade,
        "direction": item["direction"],
        "direction_zh": DIRECTIONS[item["direction"]],
        "model_probability_uncalibrated": round(probability, 6),
        "model_probabilities_1x2": model,
        "earlier_market_consensus_probabilities_1x2": consensus,
        "market_direction_agrees": item["market_direction_agrees"] is True,
        "reason": ("MODEL_MARKET_AGREED_AND_RESEARCH_THRESHOLD"
                   if grade == "A_RESEARCH" else
                   "MODEL_MARKET_DISAGREEMENT"
                   if item["market_direction_agrees"] is False else
                   "BELOW_RESEARCH_THRESHOLD"),
        "bookmaker_decimal_odds": None,
        "settled_result": None,
        "research_selection_not_profitable_bet": True,
        "qualifies_for_value_recommendation": False,
        "production_recommendations": "DISABLED",
    }

def build(shadow, pairing, status, market_status, fixture_integrity, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_TIME")
    audited = shortlist_build(
        shadow, pairing, status,
        market_status=market_status, fixture_integrity=fixture_integrity,
        now=now, max_selections=MAX_VERIFICATION_ROWS,
        max_reviews=MAX_VERIFICATION_ROWS)
    base = {
        "schema": "football-king-forward-pick-verification-slate-v1",
        "generated_utc": now.isoformat(),
        "status": "RESEARCH_ONLY" if audited["status"] == "RESEARCH_ONLY" else "HOLD",
        "research_only": True,
        "production_recommendations": "DISABLED",
        "official_betting_recommendations": 0,
        "value_recommendations": [],
        "verified_ev": False,
        "executably_quoted_odds_present": False,
        "model_calibrated": False,
        "point_in_time_market_pairs": audited["paired_count"],
        "a_research_directions": 0,
        "b_verification_directions": 0,
        "verification_rows": 0,
        "not_shown_due_to_bound": 0,
        "no_result_injected_into_prediction": True,
        "source_diagnostics": audited.get("diagnostics", {}),
        "rows": [],
        "notice": ("以下係開賽前封存嘅未校準1X2模型選向，"
                   "A級只代表與市場方向一致及研究門檻；B級包含市場分歧，"
                   "兩者都唔係已驗證可下注正EV。賽後需逐場追蹤，不能只計贏嘅場次。"),
    }
    if audited["status"] != "RESEARCH_ONLY":
        return {**base,"status":"HOLD"}
    rows, seen = [], set()
    for tier, group in (
            ("A_RESEARCH", audited["selections"]),
            ("B_VERIFICATION_ONLY", audited["reviews"])):
        for item in group:
            try:
                row = _make_row(item, tier)
                key = (row["league"], row["home"], row["away"], row["kickoff_utc"])
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)
            except (ValueError, KeyError, TypeError, OverflowError):
                continue
    rows.sort(key=lambda r: (
        0 if r["research_tier"] == "A_RESEARCH" else 1,
        -r["model_probability_uncalibrated"], r["kickoff_utc"], r["sealed_pick_digest"]))
    rows = rows[:MAX_VERIFICATION_ROWS]
    return {
        **base,
        "a_research_directions": sum(r["research_tier"]=="A_RESEARCH" for r in rows),
        "b_verification_directions": sum(r["research_tier"]=="B_VERIFICATION_ONLY" for r in rows),
        "verification_rows": len(rows),
        "not_shown_due_to_bound": max(0, audited["paired_count"]-len(rows)
                                          -sum(audited.get("excluded_reasons",{}).values())),
        "rows": rows,
    }

def _csv_safe(value):
    value = str(value)
    # Spreadsheet formula injection protection for scraped team names.
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value

def as_csv(report):
    buf=io.StringIO()
    writer=csv.writer(buf,lineterminator="\n")
    columns=("sealed_pick_digest","research_tier","league","home","away",
             "kickoff_hong_kong","kickoff_utc","prediction_utc","direction_zh",
             "model_probability_uncalibrated","market_direction_agrees",
             "settled_result","production_recommendations")
    writer.writerow(columns)
    for row in report["rows"]:
        writer.writerow([_csv_safe(row.get(k,"") if row.get(k) is not None else "")
                         for k in columns])
    return buf.getvalue()

def render(report):
    if report["production_recommendations"]!="DISABLED":
        raise ValueError("UNSAFE_SUGGESTIONS")
    esc=html.escape
    grouped=Counter(r["league"] for r in report["rows"])
    out=[
        '<section id="fk-verification-slate" role="region">',
        '<h2>逐場核實｜完整賽前研究選向</h2>',
        '<p><strong>可核對 '+str(report["verification_rows"])+' 場</strong>；'
        'A級研究 '+str(report["a_research_directions"])+' 場；'
        'B級分歧／觀察 '+str(report["b_verification_directions"])+' 場。</p>',
        '<p class="small"><strong>即場安全警告：</strong>呢份係賽前封存研究名單，並非即時比分或即場投注推薦。比賽開波後，賽前概率及盤口全部失效；未經兩個獨立來源確認最新比分、並建立獨立驗證嘅即場模型前，一律停止即場推薦。</p>',
        '<p class="small">唔會為湊數亂推：每場都有開賽、預測及較早市場時間。'
        'A/B 唔代表投注勝算認證；未有實際可成交賠率，正式推薦仍暫停。'
        '賽後需要連輸嘅場次一齊統計。</p>',
        '<p><a href="verification_slate.csv">下載逐場核對 CSV</a>｜'
        '<a href="verification_slate.json">查看完整機率及核對 ID</a></p>',
    ]
    for league in LEAGUES:
        rows=[r for r in report["rows"] if r["league"]==league]
        if not rows:
            continue
        out.append('<details'+(' open' if league=="epl" else '')+'>'
                   '<summary>'+esc(LEAGUE_NAMES[league])+'（'+str(grouped[league])+' 場）</summary><ol>')
        for r in rows:
            tier="A級研究" if r["research_tier"]=="A_RESEARCH" else "B級驗證"
            match=esc(r["home"])+" 對 "+esc(r["away"])
            obs=("與市場方向一致" if r["market_direction_agrees"]
                 else "與市場方向有分歧")
            out.append('<li><strong>'+match+'</strong>｜'+esc(r["kickoff_hong_kong"])+' 香港時間；'
                       +tier+'：<strong>'+esc(r["direction_zh"])+'</strong> '
                       +f'{r["model_probability_uncalibrated"]:.1%}'
                       +'（未校準）；'+obs+'。<small>記錄：'
                       +esc(r["sealed_pick_digest"][:12])+'</small></li>')
        out.append('</ol></details>')
    if not report["rows"]:
        out.append('<p>目前冇通過時間／資料核實嘅研究選向；唔會製造假推薦。</p>')
    out.append('</section>')
    return "".join(out)

def publish(site, *, now=None):
    site=Path(site)
    files=("shadow.json","market_comparison.json","status.json",
           "market_status.json","fixture_integrity.json")
    contents={k:json.loads((site/k).read_text(encoding="utf-8")) for k in files}
    report=build(contents["shadow.json"],contents["market_comparison.json"],
                 contents["status.json"],contents["market_status.json"],
                 contents["fixture_integrity.json"],now=now)
    page=site/"index.html"
    markup=page.read_text(encoding="utf-8")
    if 'id="fk-verification-slate"' in markup:
        raise ValueError("DUPLICATE_VERIFICATION_SLATE")
    anchor="<h2>近期賽程與賽果</h2>"
    if anchor in markup:
        markup=markup.replace(anchor,render(report)+anchor,1)
    elif "</main>" in markup:
        markup=markup.replace("</main>",render(report)+"</main>",1)
    else:
        raise ValueError("NO_SAFE_SITE_SECTION")
    (site/"verification_slate.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (site/"verification_slate.csv").write_text(as_csv(report),encoding="utf-8-sig")
    page.write_text(markup,encoding="utf-8")
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--site",default="app/site")
    a=p.parse_args()
    r=publish(a.site)
    print("VERIFICATION_SLATE:",r["status"],
          "A:",r["a_research_directions"],"B:",r["b_verification_directions"],
          "ROWS:",r["verification_rows"],"MARKET_PAIRS:",r["point_in_time_market_pairs"],
          "FORMAL_PICKS:",r["official_betting_recommendations"])

if __name__=="__main__":
    main()
