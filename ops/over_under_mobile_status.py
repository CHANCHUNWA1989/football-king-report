"""Render evidence-gated OU2.5 and actual market-coverage status on iPhone.

Only the archived no-vig 1X2 consensus is publicly available. It is NOT an
executable bookmaker quote, and does not authenticate Asian handicap/totals.
"""
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path

MARKER = '<section id="fk-ou25">'
END = '</section>'
UNVERIFIED = "市場快照缺失或無法核對；讓球盤及入球大細盤均未獲核實。"


def market_disclosure(market_file):
    """Only display a dated, schema-consistent research snapshot; never EV."""
    if market_file is None:
        return UNVERIFIED
    try:
        source = Path(market_file)
        if not source.is_file() or source.is_symlink() or not 0 < source.stat().st_size <= 1_000_000:
            return UNVERIFIED
        data = json.loads(source.read_text(encoding="utf-8"))
        count = data.get("event_count")
        events = data.get("events")
        valid = (
            data.get("schema") == "football-king-market-consensus-v1"
            and data.get("status") == "RESEARCH_ONLY"
            and data.get("market") == "h2h"
            and data.get("requested_markets") == ["h2h"]
            and isinstance(data.get("missing_markets"), list)
            and {"spreads", "totals"}.issubset(set(
                v for v in data["missing_markets"] if type(v) is str))
            and data.get("handicap_and_totals_verified") is False
            and type(count) is int and 0 <= count <= 1000
            and isinstance(events, list) and len(events) == count
        )
        if not valid:
            return UNVERIFIED
        stamp = datetime.fromisoformat(data["as_of_utc"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return UNVERIFIED
        timestamp = stamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return (
            f"公開市場快照（{timestamp}）：{count}場1X2去水共識概率，"
            "並非可成交賠率；亞洲讓球盤及入球大細盤均缺少可核實盤口，"
            "不能計算可執行正EV。"
        )
    except (OSError, ValueError, TypeError, KeyError, OverflowError, AttributeError):
        return UNVERIFIED


def publish(site, market_file=None):
    site = Path(site)
    data = json.loads((site / "over_under_25.json").read_text(encoding="utf-8"))
    count = data.get("candidate_count")
    if (type(count) is not int or count < 0
            or data.get("production_recommendations") != "DISABLED"
            or (data.get("input_status") == "NO_VERIFIED_MARKET_INPUT"
                and count != 0)):
        raise ValueError("INVALID_OU25_RESEARCH_STATUS")
    status = html.escape(str(data.get("input_status", "UNKNOWN"))[:100])
    updated = html.escape(str(data.get("generated_at_utc", "UNKNOWN"))[:60])
    coverage = html.escape(market_disclosure(market_file))
    notice = ("目前未有已核實大細球候選，唔代表系統推薦細球或大球。"
              if count == 0 else "研究候選未經獨立驗證，不屬正式投注推薦。")
    section = (MARKER + "<h2>亞洲讓球／大細 2.5 市場核實</h2>"
               + "<p>大細研究候選：" + str(count) + "；正式投注推薦：停用</p>"
               + "<p>輸入狀態：" + status + "；更新：" + updated + "</p>"
               + "<p>" + coverage + "</p><p>" + notice + "</p>"
               + '<p><a href="over_under_25.json">查看大細球研究條件</a></p>' + END)
    index = site / "index.html"
    body = index.read_text(encoding="utf-8")
    if MARKER in body:
        start = body.index(MARKER)
        end = body.find(END, start)
        if end < 0:
            raise ValueError("BROKEN_OU25_SECTION")
        body = body[:start] + section + body[end + len(END):]
    elif "</main>" in body:
        body = body.replace("</main>", section + "</main>", 1)
    elif "</body>" in body:
        body = body.replace("</body>", section + "</body>", 1)
    else:
        raise ValueError("NO_HTML_INSERTION_POINT")
    index.write_text(body, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", required=True)
    parser.add_argument("--market")
    args = parser.parse_args()
    publish(args.site, args.market)
