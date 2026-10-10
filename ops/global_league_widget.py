"""Render searchable worldwide league coverage on the static mobile website."""
import argparse
import html
import json
from pathlib import Path

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
        '</section><link rel="stylesheet" href="global_league_catalog.css">'
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
            "production_recommendations": "DISABLED"}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--site", default="app/site")
    args = p.parse_args()
    print(json.dumps(inject(args.site), ensure_ascii=False))
