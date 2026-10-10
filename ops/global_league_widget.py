"""Render searchable worldwide league coverage on the static mobile website."""
import argparse
import html
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

STATES = {
    "UNCALIBRATED_SHADOW": "已有未校準 Shadow 研究預測",
    "CURRENT_SOURCE_NO_FORECAST": "有當季來源，但未達模型預測要求",
    "ARCHIVE_ONLY": "只有歷史來源",
    "DISCOVERED_UNVERIFIED": "發現當季檔案，尚未核實內容",
    "NO_VERIFIED_SOURCE": "暫未取得可信來源",
}
JS = """(function(){
'use strict';
const root = document.getElementById('fk-worldwide-directory');
const search = document.getElementById('fk-world-search');
const filter = document.getElementById('fk-world-mode');
const tally = document.getElementById('fk-world-count');
if (!root || !search || !filter || !tally) return;
const rows = root.querySelectorAll('li[data-world-league]');
function redraw() {
  const q = search.value.trim().toLocaleLowerCase();
  const mode = filter.value;
  let n = 0;
  for (const row of rows) {
    const matchText = (row.getAttribute('data-search') || '').toLocaleLowerCase();
    const matchMode = row.getAttribute('data-mode') === mode || mode === 'ALL';
    row.hidden = !(matchMode && (!q || matchText.includes(q)));
    if (!row.hidden) n++;
  }
  tally.textContent = String(n);
}
search.addEventListener('input', redraw);
filter.addEventListener('change', redraw);
redraw();
})();"""
CSS = """#fk-worldwide-directory{padding:15px;border:1px solid #64748b66;border-radius:15px;margin:16px 0}
#fk-worldwide-directory h2{font-size:1.1rem;margin:0 0 6px}
#fk-worldwide-directory label{margin-right:6px;font-weight:600}
#fk-worldwide-directory input,#fk-worldwide-directory select{min-height:38px;margin:4px 8px 4px 0;padding:7px;border:1px solid #64748b88;border-radius:8px;max-width:100%}
#fk-worldwide-directory ul{max-height:440px;overflow-y:auto;padding-left:24px}
#fk-worldwide-directory li{padding:4px 0;line-height:1.45}
#fk-worldwide-directory li[hidden]{display:none}
#fk-worldwide-directory p{line-height:1.5}
"""


def inject(site):
    site = Path(site)
    index = site / "index.html"
    body = index.read_text(encoding="utf-8")
    if "</body>" not in body or 'id="fk-worldwide-directory"' in body:
        raise ValueError("BAD_OR_DUPLICATE_WORLD_DIRECTORY_PAGE")
    try:
        doc = json.loads((site / "global_league_catalog.json").read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, OSError):
        doc = {}
    verified = (isinstance(doc, dict)
                and doc.get("schema") == "football-king-global-league-catalog-v1"
                and doc.get("production_recommendations") == "DISABLED"
                and doc.get("executable_odds_confirmed") is False
                and doc.get("all_world_leagues_complete") is False
                and isinstance(doc.get("cards"), list))
    cards = doc["cards"][:400] if verified else []
    out = []
    for row in cards:
        if not isinstance(row, dict) or row.get("coverage_state") not in STATES:
            continue
        code = str(row.get("id") or "")[:48]
        name = str(row.get("name") or code)[:70]
        n = row.get("shadow_predictions")
        n = n if type(n) is int and 0 <= n <= 2500 else 0
        mode = row["coverage_state"]
        find = html.escape((name + " " + code).lower(), quote=True)
        out.append(
            '<li data-world-league="1" data-mode="' + html.escape(mode, quote=True) +
            '" data-search="' + find + '"><strong>' + html.escape(name) +
            '</strong>（' + html.escape(code) + '）：' +
            html.escape(STATES[mode]) + '；Shadow ' + str(n) + ' 場</li>'
        )
    total = len(out)
    shadow = doc.get("leagues_with_shadow", 0) if verified else 0
    shadow = shadow if type(shadow) is int and 0 <= shadow <= total else 0
    try:
        worldwide = json.loads((site / "worldwide_source_status.json").read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, OSError):
        worldwide = {}
    research_source_ok = (
        isinstance(worldwide, dict)
        and worldwide.get("schema") == "football-king-worldwide-source-build-status-v1"
        and worldwide.get("production_recommendations") == "DISABLED"
        and worldwide.get("status") in ("HOLD", "RESEARCH_ONLY")
    )
    if research_source_ok:
        def safe_count(key):
            number = worldwide.get(key)
            return number if type(number) is int and 0 <= number <= 100000 else 0
        source_text = (
            "全球額外資料採集：抽樣研究聯賽 " + str(safe_count("requested_leagues")) +
            " 個、讀取歷史賽果 " + str(safe_count("historical_games")) +
            " 場、獨立賽程時間一致 " +
            str(safe_count("two_source_schedule_agreements")) +
            " 場。資料仍未獨立核實，不等於可下注。"
        )
    else:
        source_text = "全球額外賽程／歷史資料來源狀態未完成驗證。"
    # Publish only previously sealed pre-match worldwide Shadow probabilities.
    # Do not transform a catalogue entry into a model, or a model into a bet.
    try:
        world_doc = json.loads((site / "worldwide_shadow.json").read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, OSError):
        world_doc = {}
    now = datetime.now(timezone.utc)
    verified_world = (
        isinstance(world_doc, dict)
        and world_doc.get("schema") == "football-king-worldwide-uncalibrated-shadow-v1"
        and world_doc.get("status") == "SHADOW_ONLY"
        and world_doc.get("production_recommendations") == "DISABLED"
        and world_doc.get("model_calibrated") is False
        and world_doc.get("market_odds_available") is False
        and world_doc.get("positive_ev_verified") is False
        and isinstance(world_doc.get("predictions"), list)
    )
    world_rows = []
    if verified_world:
        try:
            asof = datetime.fromisoformat(world_doc["as_of_utc"].replace("Z", "+00:00"))
            verified_world = (asof.tzinfo is not None and
                              timedelta(minutes=-5) <=
                              now - asof.astimezone(timezone.utc) <= timedelta(hours=10))
        except (KeyError, AttributeError, TypeError, ValueError, OverflowError):
            verified_world = False
    if verified_world:
        entries = []
        for case in world_doc["predictions"][:500]:
            if (not isinstance(case, dict)
                    or case.get("production_recommendations") != "DISABLED"
                    or case.get("calibrated") is not False
                    or case.get("verified_market_odds") is not False
                    or case.get("worldwide_two_distinct_schedule_feeds") is not True):
                continue
            h, a, league = case.get("home"), case.get("away"), case.get("league")
            probs = [case.get(k) for k in ("p_home", "p_draw", "p_away")]
            if (not all(isinstance(v, str) and 1 <= len(v) <= 100 for v in (h, a, league))
                    or not all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in probs)
                    or abs(sum(probs) - 1) > .002):
                continue
            try:
                kickoff = datetime.fromisoformat(case["kickoff_utc"].replace("Z", "+00:00"))
                forecast = datetime.fromisoformat(case["prediction_utc"].replace("Z", "+00:00"))
                if kickoff.tzinfo is None or forecast.tzinfo is None:
                    continue
                kickoff, forecast = (kickoff.astimezone(timezone.utc),
                                     forecast.astimezone(timezone.utc))
                if (not forecast <= now < kickoff - timedelta(minutes=10)
                        or kickoff - now > timedelta(days=7)):
                    continue
            except (KeyError, ValueError, TypeError, AttributeError, OverflowError):
                continue
            labels = ("主勝", "和局", "客勝")
            top = max(range(3), key=lambda i: probs[i])
            local = kickoff.astimezone(ZoneInfo("Asia/Hong_Kong"))
            entries.append((kickoff, 
                '<li><strong>' + html.escape(h) + ' vs ' + html.escape(a) +
                '</strong>｜' + html.escape(league) +
                '｜香港 ' + local.strftime("%m/%d %H:%M") +
                '｜Shadow：' + labels[top] + ' ' +
                format(probs[top] * 100, ".1f") +
                '%（主／和／客 ' + " / ".join(format(p * 100, ".1f") + "%" for p in probs) +
                '）。未校準；冇可成交賠率，唔係投注推薦。</li>'))
        world_rows = [x[1] for x in sorted(entries)[:12]]
    other_league_section = (
        '<section id="fk-worldwide-forecast" aria-label="其他聯賽未校準預測">'
        '<h2>其他聯賽｜即將開賽 Shadow 研究方向</h2>'
        '<p>只列已封存、時間未過期、雙來源核對嘅比賽；'
        '並非即時可成交正EV推薦。</p>'
        '<ul>' + (''.join(world_rows) if world_rows else
        '<li>目前沒有合資格、尚未開賽嘅其他聯賽模型預測；保持 HOLD。</li>') +
        '</ul><p><a href="worldwide_shadow.json">查看原始模型概率與證據</a></p></section>')
    section = (
        '<section id="fk-worldwide-directory" aria-label="全球足球聯賽資料及模型覆蓋">'
        '<h2>全球足球聯賽搜尋及研究覆蓋</h2>'
        '<p>已登記 '+str(total)+' 個不同聯賽；其中 '+str(shadow)+
        ' 個有 Shadow 研究預測。可按名稱或代碼搜尋。</p>'
        '<p class="fk-note" id="fk-world-provenance">' +
        html.escape(source_text) +
        ' <a href="worldwide_source_status.json">全球採集診斷</a></p>'
        '<label for="fk-world-search">聯賽搜尋</label>'
        '<input type="search" id="fk-world-search" placeholder="例如：日本、荷甲、MLS" />'
        '<label for="fk-world-mode">資料狀態</label>'
        '<select id="fk-world-mode">'
        '<option value="ALL">所有聯賽</option>'
        '<option value="UNCALIBRATED_SHADOW">有Shadow模型</option>'
        '<option value="CURRENT_SOURCE_NO_FORECAST">有當季資料</option>'
        '<option value="ARCHIVE_ONLY">只有歷史資料</option>'
        '<option value="DISCOVERED_UNVERIFIED">新發現未驗證</option>'
        '<option value="NO_VERIFIED_SOURCE">未取得來源</option>'
        '</select>'
        '<p>符合條件：<strong id="fk-world-count">'+str(total)+'</strong> 個聯賽</p>'
        '<ul id="fk-world-results">'+''.join(out)+'</ul>'
        '<p>自動探索唔等於全球所有聯賽已齊全；有聯賽資料亦唔代表'
        '有可靠 UTC 時間、已校準模型或可成交博彩公司賠率。'
        '未通過核實嘅聯賽只供查閱，唔會強行產生投注建議。</p>'
        '<p><a href="global_league_catalog.json">完整來源及逐聯賽預測資格</a></p>'
        '</section>' + other_league_section + '<link rel="stylesheet" href="global_league_catalog.css">'
        '<script src="global_league_catalog.js" defer></script>'
    )
    marker = '<h2>近期賽程與賽果</h2>'
    if marker in body:
        body = body.replace(marker, section + marker, 1)
    else:
        body = body.replace("</body>", section + "</body>", 1)
    index.write_text(body, encoding="utf-8")
    (site / "global_league_catalog.css").write_text(CSS + "\n", encoding="utf-8")
    (site / "global_league_catalog.js").write_text(JS + "\n", encoding="utf-8")
    return {"status": "RESEARCH_ONLY" if verified else "HOLD",
            "catalogue_rows": total, "with_shadow": shadow,
            "upcoming_worldwide_shadow_cases": len(world_rows),
            "production_recommendations": "DISABLED"}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--site", default="app/site")
    args = p.parse_args()
    print(json.dumps(inject(args.site), ensure_ascii=False))
