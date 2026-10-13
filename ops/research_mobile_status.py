"""Expose honest model research status in the published mobile HTML."""
import argparse
import html
import json
from pathlib import Path


def publish(site):
    site = Path(site)
    report = json.loads((site / "unified_research.json").read_text(encoding="utf-8"))
    reason = html.escape(str(report.get("reason", "NO_VERIFIED_EVIDENCE"))[:180])
    status = html.escape(str(report.get("status", "HOLD"))[:40])
    n = report.get("accuracy_audit")
    count = n.get("n", 0) if isinstance(n, dict) else 0
    count = count if type(count) is int and count >= 0 else 0
    section = ('<section id="fk-unified-research"><h2>每日模型與市場驗證</h2>'
               '<p>狀態：<b>' + status + '</b>；已驗證樣本：' + str(count) + '</p>'
               '<p>原因：' + reason + '</p>'
               '<p>研究用途，尚未證明可持續擊敗市場或達到70%命中率。</p>'
               '<p><a href="unified_research.json">查看完整模型比較及缺失證據</a></p></section>')
    index = site / "index.html"
    body = index.read_text(encoding="utf-8")
    marker = '<section id="fk-unified-research">'
    if marker in body:
        start = body.index(marker)
        end = body.find("</section>", start)
        if end < 0:
            raise ValueError("BROKEN_EXISTING_RESEARCH_SECTION")
        body = body[:start] + section + body[end + len("</section>"):]
    elif "</main>" in body:
        body = body.replace("</main>", section + "</main>", 1)
    elif "</body>" in body:
        body = body.replace("</body>", section + "</body>", 1)
    else:
        raise ValueError("MISSING_HTML_INSERTION_POINT")
    index.write_text(body, encoding="utf-8")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--site", default="app/site")
    publish(p.parse_args().site)
