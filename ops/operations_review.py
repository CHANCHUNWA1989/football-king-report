"""Read-only operational dashboard over existing daily report artifacts.

Counts are observations, not global unique fixtures or independently verified
results. Missing/unsafe data stays unknown, not zero. No network or actions.
"""
import argparse
import html
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HK = ZoneInfo("Asia/Hong_Kong")
FILES = ("quality","worldwide_source_status","worldwide_shadow","market_status",
         "production_gate","competitive_guard","forward_daily_scorecard")
OPTIONAL = ("global_full_slate","unified_market_grid")
LIMIT = 20_000_000

def count(doc, key):
    v=doc.get(key)
    return v if type(v) is int and 0<=v<=1_000_000 else None

def clock(value):
    if not isinstance(value,str):
        raise ValueError("MISSING_CLOCK")
    t=datetime.fromisoformat(value.replace("Z","+00:00"))
    if t.tzinfo is None:
        raise ValueError("NAIVE_CLOCK")
    return t.astimezone(timezone.utc)

def build(documents, *, now=None):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    alerts=[]
    states={}
    safe={}
    def alert(code, priority):
        alerts.append({"code":code,"priority":priority})
    for name in FILES+OPTIONAL:
        doc=documents.get(name)
        if not isinstance(doc,dict):
            states[name]="MISSING_OR_INVALID"
            if name in FILES: alert("MISSING_"+name.upper(),"P1")
        elif doc.get("production_recommendations")!="DISABLED":
            states[name]="UNSAFE"
            alert("UNSAFE_"+name.upper(),"P0")
        else:
            safe[name]=doc
            states[name]="RESEARCH_METADATA_ONLY"
    q=safe.get("quality",{})
    w=safe.get("worldwide_source_status",{})
    s=safe.get("worldwide_shadow",{})
    m=safe.get("market_status",{})
    g=safe.get("production_gate",{})
    d=safe.get("forward_daily_scorecard",{})
    c=safe.get("competitive_guard",{})
    counts={"public_window_observations":count(q,"public_matches"),
            "precise_kickoff_observations":count(q,"matches_with_precise_kickoff"),
            "worldwide_requested_leagues":count(w,"requested_leagues"),
            "worldwide_eligible_leagues":count(w,"eligible_catalogue_leagues"),
            "worldwide_schedule_agreements":count(w,"two_source_schedule_agreements"),
            "worldwide_shadow_predictions":count(s,"predictions_count"),
            "time_valid_market_pairs":count(m,"matched_count"),
            "recorded_settled_research":count(d,"settled_observations"),
            "gate_recorded_settled_research":count(g,"settled_samples")}
    for key,value in counts.items():
        if value is None: alert("UNKNOWN_"+key.upper(),"P1")
    a,b=counts["recorded_settled_research"],counts["gate_recorded_settled_research"]
    if a is not None and b is not None and a!=b:
        alert("SETTLED_REPORT_COUNT_MISMATCH","P0")
    if g and (g.get("status")!="HOLD" or g.get("model_promoted") is not False):
        alert("GATE_STATE_UNSAFE","P0")
    try:
        age=now-clock(m.get("market_as_of_utc"))
        market_age_hours=round(age.total_seconds()/3600,2)
        if not timedelta(0)<=age<=timedelta(hours=10):
            alert("MARKET_CLOCK_STALE_OR_FUTURE","P1")
    except (ValueError,TypeError,OverflowError):
        market_age_hours=None
        alert("MARKET_CLOCK_UNKNOWN","P1")
    if counts["time_valid_market_pairs"]==0: alert("NO_CURRENT_MARKET_PAIRS","P1")
    if counts["worldwide_schedule_agreements"]==0: alert("NO_WORLDWIDE_SCHEDULE_AGREEMENTS","P1")
    if c.get("model_currently_behind_market_on_both_scores") is True:
        alert("MODEL_TRAILS_MARKET_DESCRIPTIVE","P1")
    # Only allowlisted scalar counters, no raw provider error strings, odds or IDs.
    review=d.get("error_review")
    review=review.get("summary") if isinstance(review,dict) else None
    error_counts={k:count(review or {},k) for k in (
        "observations","model_correct","model_incorrect","market_correct",
        "market_incorrect","model_wrong_market_right","model_right_market_wrong")}
    if a is not None and error_counts["observations"] not in (None,a):
        alert("ERROR_REVIEW_COUNT_MISMATCH","P0")
    if a is not None and a<300: alert("RESEARCH_SAMPLE_TARGET_NOT_MET","P1")
    # Optional prior phases are not presumed deployed.
    return {"schema":"football-king-operations-review-center-v1",
            "generated_utc":now.isoformat(),"generated_hk":now.astimezone(HK).isoformat(),
            "status":"HOLD","production_recommendations":"DISABLED",
            "automatic_model_changes":False,"automatic_bets":False,
            "global_coverage_complete":False,"authenticated_forward_samples":0,
            "positive_ev_verified":False,"source_states":states,
            "counts":counts,"market_age_hours":market_age_hours,
            "descriptive_error_counts":error_counts,"alerts":alerts,
            "technical_alert_count":len(alerts),"zero_extra_api_calls":True}

def load(path):
    try:
        with path.open("rb") as f:
            raw=f.read(LIMIT+1)
        if len(raw)>LIMIT: return None
        return json.loads(raw)
    except (OSError,ValueError,UnicodeError):
        return None

def publish(site, *, now=None):
    site=Path(site)
    report=build({name:load(site/(name+".json")) for name in FILES+OPTIONAL},now=now)
    esc=html.escape
    def cells(mapping):
        return "".join("<tr><th>"+esc(k)+"</th><td>"+esc("未知" if v is None else str(v))+"</td></tr>" for k,v in mapping.items())
    page=("<!doctype html><html lang='zh-Hant'><meta charset='utf-8'>"
          "<meta name='viewport' content='width=device-width,initial-scale=1'>"
          "<title>足球王者運行監控</title><style>body{font-family:system-ui;margin:18px;max-width:900px}"
          "table{border-collapse:collapse;width:100%;overflow-wrap:anywhere}th,td{padding:7px;border-bottom:1px solid #aaa;text-align:left}</style>"
          "<h1>足球王者運行監控｜HOLD</h1><p>研究資料，未獨立認證，不代表完整全球覆蓋。</p>"
          "<p>"+esc(report["generated_hk"])+"</p><h2>覆蓋與結算</h2><table>"+cells(report["counts"])+"</table>"
          "<h2>錯例統計（描述性）</h2><table>"+cells(report["descriptive_error_counts"])+"</table>"
          "<h2>待處理問題</h2><ul>"+"".join("<li>"+esc(a["priority"]+" "+a["code"])+"</li>" for a in report["alerts"])+"</ul>"
          "<h2>來源狀態</h2><table>"+cells(report["source_states"])+"</table>"
          "<p><a href='operations_review.json'>下載監控資料</a> · <a href='daily-review.html'>每日復盤</a> · <a href='index.html'>首頁</a></p></html>")
    (site/"operations_review.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (site/"operations-review.html").write_text(page,encoding="utf-8")
    index=site/"index.html"
    markup=index.read_text(encoding="utf-8")
    if 'id="operations-review-nav"' not in markup:
        link='<p id="operations-review-nav"><a href="operations-review.html">全盤運行監控及復盤中心</a></p>'
        pos=markup.lower().rfind("</body>")
        if pos<0: raise ValueError("NO_SAFE_HTML_INSERTION")
        index.write_text(markup[:pos]+link+markup[pos:],encoding="utf-8")
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--site",required=True)
    r=publish(p.parse_args().site)
    print(json.dumps({"status":r["status"],"technical_alert_count":r["technical_alert_count"],
                      "production_recommendations":"DISABLED"}))
