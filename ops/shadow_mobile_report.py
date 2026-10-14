"""Generate a phone-readable, fail-closed daily research status from verified pipeline artifacts."""
import argparse
import json
from pathlib import Path

def render(readiness, integrity, daily, parsed):
    if any(x.get("production_recommendations")!="DISABLED" for x in (readiness,integrity,daily,parsed)):
        raise ValueError("PRODUCTION_FLAG_UNSAFE")
    if readiness.get("status")!="HOLD" or daily.get("status")!="SHADOW_ONLY":
        raise ValueError("UNSAFE_RESEARCH_STATUS")
    if integrity.get("status")!="PASS":
        raise ValueError("INTEGRITY_NOT_CONFIRMED")
    n=readiness.get("valid_scored_fixtures")
    target=readiness.get("target")
    if type(n) is not int or type(target) is not int or n<0 or target<=0 or n>target:
        raise ValueError("INVALID_SAMPLE_COUNTER")
    if daily.get("valid_fixtures")!=n:
        raise ValueError("SAMPLE_COUNTER_MISMATCH")
    lines=["# 足球王者｜每日研究狀態","",
           "**研究模式：SHADOW ONLY｜正式推薦：DISABLED**","",
           f"- 有效獨立驗證樣本：**{n}/{target}**",
           f"- 尚待完場核實：**{readiness.get('matured_awaiting_ft',0)}** 場",
           f"- 結構化來源過期（14日）：**{readiness.get('source_stale_14d')}**",
           f"- 完整性閘門：**{integrity.get('status')}**","",
           "## 數據來源健康度","",
           "| 來源 | 已解析完場記錄 | 來源狀態 |",
           "|---|---:|---|"]
    for source in parsed.get("sources",[]):
        provider=source.get("provider","UNKNOWN")
        if provider not in ("OpenLigaDB","OpenFootball"):
            raise ValueError("UNKNOWN_PROVIDER")
        records=source.get("records",[])
        if not isinstance(records,list):
            raise ValueError("INVALID_RECORDS")
        lines.append(f"| {provider} | {len(records)} | 尚未獨立驗證 |")
    if not parsed.get("sources"):
        lines.append("| 無可用來源 | 0 | HOLD |")
    lines+=["","## 未解決阻礙",""]
    reasons=readiness.get("blocking_reasons",[])
    if not isinstance(reasons,list):
        raise ValueError("INVALID_BLOCKERS")
    lines += [f"- `{reason}`" for reason in reasons] if reasons else ["- 暫無已報告阻礙；仍不可啟用正式推薦"]
    lines+=["","## 原則","",
            "只使用賽前封存預測與可追溯、相互獨立嘅完場證據評分；未核實、重複、過期或矛盾資料一律唔當作命中。",
            "本報告不構成投注推薦。",""]
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    for key in ("readiness","integrity","daily","parsed","output"):
        p.add_argument("--"+key,required=True)
    a=p.parse_args()
    data=[json.loads(Path(getattr(a,k)).read_text(encoding="utf-8")) for k in ("readiness","integrity","daily","parsed")]
    out=Path(a.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(render(*data),encoding="utf-8")

if __name__=="__main__":
    main()
