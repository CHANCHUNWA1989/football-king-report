"""No-credit Friday research quality summary using sealed results and market metadata.

This is an OPERATIONS AND EMPIRICAL-VALIDATION report, NOT auto-curated
external football papers or any bet recommendation. Runs with zero odds calls.
"""
import argparse
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from research_center import metrics

NAMES={"epl":"英超","championship":"英冠","bundesliga":"德甲",
       "laliga":"西甲","seriea":"意甲","ligue1":"法甲"}
LEAGUES=tuple(NAMES)


def clock(value):
    t=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if t.tzinfo is None:raise ValueError("NAIVE_WEEKLY_TIME")
    return t.astimezone(timezone.utc)


def digest(evidence,market,now=None):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError("NAIVE_NOW")
    if evidence.get("production_recommendations")!="DISABLED":
        raise ValueError("UNSAFE_WEEKLY_EVIDENCE")
    if market.get("production_recommendations")!="DISABLED":
        raise ValueError("UNSAFE_WEEKLY_MARKET")
    rows=evidence.get("samples",[])
    if not isinstance(rows,list) or evidence.get("n")!=len(rows):
        raise ValueError("MISMATCHED_WEEKLY_SAMPLES")
    start=now-timedelta(days=7)
    weekly=[]
    for row in rows:
        if not isinstance(row,dict):
            continue
        try:
            time=clock(row["kickoff_utc"])
            if start<=time<=now:
                weekly.append(row)
        except (KeyError,TypeError,ValueError,OverflowError):
            continue
    by_league={league:metrics([r for r in weekly if r.get("league")==league])
               for league in LEAGUES}
    all_time=metrics(rows)
    q=market.get("quota") or {}
    age=None
    try:age=round((now-clock(market["as_of_utc"])).total_seconds()/3600,1)
    except (KeyError,TypeError,ValueError,OverflowError):pass
    warnings=[]
    if age is None or age>26 or age<-.1:warnings.append("免費賠率快照超過26小時或時間不明")
    if not isinstance(q.get("remaining"),int):warnings.append("API積分餘額未知")
    elif q["remaining"]<=145:warnings.append("免費API餘額接近安全保留線")
    if not rows:warnings.append("尚未累積可以核對市場的完場樣本")
    if any(r.get("fixture_result_source_independently_verified") is not True for r in rows):
        warnings.append("已結算賽果未全部獲第二獨立來源核對")
    if all_time and all_time["market_minus_model_log_loss"]<0 and len(rows)>=50:
        warnings.append("探索性Log Loss顯示模型落後市場；不得據此判定統計顯著")
    return {
        "as_of_utc":now.isoformat(),
        "window_start_utc":start.isoformat(),
        "last_7d_settled":len(weekly),
        "all_time_settled":len(rows),
        "free_quota":q,"market_age_hours":age,
        "model_vs_market":all_time,
        "weekly_by_league":by_league,
        "warnings":warnings,
        "production_recommendations":"DISABLED",
    }


def to_markdown(report):
    fmt=lambda x:"—" if x is None else str(x)
    q=report["free_quota"]
    lines=[
        "# 足球王者 V4.1｜每週研究可靠性報告",
        "",
        "> 只供研究，並非投注建議；模型未獨立證實有市場優勢。",
        "",
        f"- 統計截止（UTC）：{report['as_of_utc']}",
        f"- 最近7日已結算可比較樣本：**{report['last_7d_settled']}**",
        f"- 歷史累積已結算可比較樣本：**{report['all_time_settled']}**",
        f"- 免費賠率API剩餘積分：**{fmt(q.get('remaining'))}**",
        f"- 最新賠率來源距現在：**{fmt(report['market_age_hours'])} 小時**",
        "- 正式投注建議：**HOLD / DISABLED**",
        "",
        "## 六大聯賽上週樣本外研究",
        "",
        "| 聯賽 | 已結算樣本 | 模型Log Loss | 市場Log Loss |",
        "|---|---:|---:|---:|",
    ]
    for key,name in NAMES.items():
        m=report["weekly_by_league"][key]
        lines.append(f"| {name} | {m['settled_games'] if m else 0} | "+
                     f"{fmt(m['model_log_loss'] if m else None)} | "+
                     f"{fmt(m['market_log_loss'] if m else None)} |")
    lines+=["","## 保留意見／風險"]
    lines.extend("- "+w for w in report["warnings"])
    if not report["warnings"]:lines+=["- 暫未偵測到額外操作警告；唔代表模型具盈利能力。"]
    lines+=["","## 研究採納判準",
            "",
            "新模型只能進入 Shadow Mode；須有同場同時嘅A/B、足量前瞻樣本、可核實市場時間、獨立賽果、分週穩定性及市場基準。",
            "輸出較好嘅單週平均分並不構成採納理由，更唔會啟用投注。",
            "",
            "完整執行狀態：https://github.com/CHANCHUNWA1989/football-king-report/actions",
            ""]
    return "\n".join(lines)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--evidence",default="evidence/settled.json")
    p.add_argument("--market",default="market/latest.json")
    p.add_argument("--out",required=True)
    args=p.parse_args()
    evidence=json.loads(Path(args.evidence).read_text(encoding="utf-8")) if Path(args.evidence).is_file() else {
        "n":0,"samples":[],"production_recommendations":"DISABLED"}
    market=json.loads(Path(args.market).read_text(encoding="utf-8")) if Path(args.market).is_file() else {
        "status":"HOLD","quota":{},"production_recommendations":"DISABLED"}
    content=to_markdown(digest(evidence,market))
    Path(args.out).parent.mkdir(parents=True,exist_ok=True)
    Path(args.out).write_text(content,encoding="utf-8")
    print(json.dumps({"written":args.out,"contains_betting_advice":False},ensure_ascii=False))


if __name__=="__main__":
    main()
