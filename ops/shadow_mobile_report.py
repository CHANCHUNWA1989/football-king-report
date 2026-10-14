"""Generate a phone-readable, fail-closed daily research status from verified pipeline artifacts."""
import argparse
import json
from pathlib import Path
from datetime import date, timedelta

def render(readiness, integrity, daily, parsed, global_coverage=None):
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
    recent=(date.today()-timedelta(days=14)).isoformat()
    for source in parsed.get("sources",[]):
        provider=source.get("provider","UNKNOWN")
        if provider not in ("OpenLigaDB","OpenFootball"):
            raise ValueError("UNKNOWN_PROVIDER")
        records=source.get("records",[])
        if not isinstance(records,list):
            raise ValueError("INVALID_RECORDS")
        dates=[row.get("date") or str(row.get("kickoff_utc",""))[:10] for row in records if isinstance(row,dict)]
        latest=max((day for day in dates if isinstance(day,str) and len(day)==10 and day<=date.today().isoformat()),default=None)
        freshness="無完場記錄" if latest is None else ("過期" if latest<recent else "近期")
        lines.append(f"| {provider} | {len(records)} | {freshness}；最新 {latest or '無'}；尚未獨立驗證 |")
    if not parsed.get("sources"):
        lines.append("| 無可用來源 | 0 | HOLD |")
    if global_coverage is not None:
        if (global_coverage.get("status")!="HOLD"
            or global_coverage.get("production_recommendations")!="DISABLED"
            or global_coverage.get("eligible_for_model_scoring") is not False
            or global_coverage.get("independently_verified") is not False
            or global_coverage.get("source_independence")!="SINGLE_PUBLISHER"):
            raise ValueError("UNSAFE_GLOBAL_COVERAGE")
        leagues=global_coverage.get("leagues")
        if not isinstance(leagues,list) or len(leagues)!=6:
            raise ValueError("INVALID_GLOBAL_COVERAGE")
        if global_coverage.get("successful_leagues")!=sum(x.get("status")=="FETCHED_UNVERIFIED" for x in leagues if isinstance(x,dict)):
            raise ValueError("GLOBAL_COVERAGE_COUNT_MISMATCH")
        lines+=["","## 全球六聯賽研究來源（單一發布者，不能計入回測）","",
                "| 聯賽 | 原始賽事 | 完場候選 | 最新完場 | 收集狀態 |",
                "|---|---:|---:|---|---|"]
        seen=set()
        for item in leagues:
            if not isinstance(item,dict) or item.get("league") in seen or not isinstance(item.get("league"),str):
                raise ValueError("INVALID_GLOBAL_LEAGUE")
            seen.add(item["league"])
            count=item.get("raw_matches")
            if type(count) is not int or count<0 or item.get("verified_results")!=0 or item.get("eligible_for_scoring") is not False:
                raise ValueError("UNSAFE_GLOBAL_LEAGUE")
            if item.get("status") not in ("FETCHED_UNVERIFIED","ERROR"):
                raise ValueError("INVALID_GLOBAL_STATUS")
            ft=item.get("finished_ft_candidates")
            last=item.get("latest_finished_date")
            if type(ft) is not int or not 0<=ft<=count or (last is not None and (not isinstance(last,str) or len(last)!=10)):
                raise ValueError("INVALID_GLOBAL_FT_COUNT")
            lines.append(f"| {item['league']} | {count} | {ft} | {last or '無'} | {item['status']} |")
    queue=readiness.get("research_queue",[])
    if not isinstance(queue,list) or len(queue)!=readiness.get("matured_awaiting_ft"):
        raise ValueError("RESEARCH_QUEUE_MISMATCH")
    lines+=["","## 已開賽但仍待核實賽果",""]
    for fixture in queue[:25]:
        if not isinstance(fixture,dict) or any(not isinstance(fixture.get(k),str) for k in ("home","away","kickoff_utc")):
            raise ValueError("INVALID_QUEUE_FIXTURE")
        home=fixture["home"].replace("|","/").replace("\n"," ")
        away=fixture["away"].replace("|","/").replace("\n"," ")
        lines.append(f"- {fixture['kickoff_utc']}｜{home} 對 {away}｜待獨立核實")
    if not queue:
        lines.append("- 暫無待核實已開賽賽事")
    if len(queue)>25:
        lines.append(f"- 其餘 {len(queue)-25} 場請查閱 research_readiness.json")
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
    p.add_argument("--global-coverage")
    a=p.parse_args()
    data=[json.loads(Path(getattr(a,k)).read_text(encoding="utf-8")) for k in ("readiness","integrity","daily","parsed")]
    out=Path(a.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    global_coverage=json.loads(Path(a.global_coverage).read_text(encoding="utf-8")) if a.global_coverage else None
    out.write_text(render(*data,global_coverage=global_coverage),encoding="utf-8")

if __name__=="__main__":
    main()
