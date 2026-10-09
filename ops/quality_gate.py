"""Production-independent provenance and quality audit for public research reports."""
import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path


def aware(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_TIME")
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("NAIVE_TIME")
    return d.astimezone(timezone.utc)


def audit(report, status, now=None):
    now = now or datetime.now(timezone.utc)
    errors, warnings = [], []
    try:
        age = (now - aware(status.get("checked_utc"))).total_seconds()
        if age < -300 or age > 36 * 3600:
            errors.append("REPORT_TIMESTAMP_OUTSIDE_ALLOWED_WINDOW")
    except (ValueError, TypeError, OverflowError):
        errors.append("INVALID_REPORT_TIMESTAMP")
    if status.get("checked_utc") != report.get("checked_utc"):
        errors.append("TIMESTAMP_MISMATCH")
    if report.get("production_recommendations") != "DISABLED" or status.get("production_recommendations") != "DISABLED":
        errors.append("PRODUCTION_RECOMMENDATIONS_NOT_DISABLED")
    sources = report.get("fixture_source_records")
    if not isinstance(sources, list) or not sources:
        errors.append("NO_SOURCE_RECORDS")
        sources = []
    successful = sum(x.get("status") == "READY_RESEARCH" for x in sources if isinstance(x, dict))
    if successful == 0:
        errors.append("NO_USABLE_PUBLIC_FIXTURE_SOURCES")
    if successful < len(sources):
        warnings.append("PARTIAL_LEAGUE_SOURCE_COVERAGE")
    upstream_known = sum(bool(x.get("upstream_updated_utc")) for x in sources if isinstance(x, dict))
    if upstream_known < len(sources):
        warnings.append("UPSTREAM_PUBLICATION_TIME_NOT_FULLY_KNOWN")
    matches = (report.get("fixtures") or {}).get("matches")
    if not isinstance(matches, list) or len(matches) > 1200:
        errors.append("MALFORMED_MATCH_COLLECTION")
        matches = []
    precise, eligible, keys = 0, 0, set()
    for match in matches:
        if not isinstance(match, dict):
            errors.append("MALFORMED_MATCH")
            continue
        key = (match.get("league"), match.get("date"), match.get("home"), match.get("away"))
        if key in keys:
            errors.append("DUPLICATE_PUBLIC_FIXTURE")
        keys.add(key)
        try:
            datetime.fromisoformat(match["date"])
        except (ValueError, TypeError, KeyError):
            errors.append("INVALID_FIXTURE_DATE")
        kickoff = match.get("kickoff_utc")
        if kickoff:
            try:
                dt = aware(kickoff)
                precise += 1
                if (dt - now).total_seconds() > 600 and match.get("score_ft") is None:
                    eligible += 1
            except (ValueError, TypeError, OverflowError):
                errors.append("INVALID_KICKOFF_TIME")
    if precise < len(matches):
        warnings.append("MATCHES_WITHOUT_VERIFIED_KICKOFF_HOUR")
    if status.get("status") not in ("HOLD", "RESEARCH_ONLY") or report.get("status") != status.get("status"):
        errors.append("INVALID_OR_INCONSISTENT_STATUS")
    grade = "HOLD" if errors or status.get("status") == "HOLD" else "RESEARCH_ONLY"
    return {
        "checked_utc": status.get("checked_utc"),
        "status": grade,
        "critical_errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "source_count": len(sources),
        "sources_usable": successful,
        "sources_with_upstream_timestamp": upstream_known,
        "public_matches": len(matches),
        "matches_with_precise_kickoff": precise,
        "pre_match_snapshot_eligible": eligible,
        "source_download_is_not_independent_fact_verification": True,
        "verified_market_odds": False,
        "validated_betting_model": False,
        "production_recommendations": "DISABLED",
    }


def apply(site, now=None):
    site = Path(site)
    report_path, status_path = site / "report.json", site / "status.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    status = json.loads(status_path.read_text(encoding="utf-8"))
    quality = audit(report, status, now=now)
    if quality["status"] == "HOLD":
        status["status"] = "HOLD"
        report["status"] = "HOLD"
    status["quality_status"] = quality["status"]
    status["quality_errors"] = quality["critical_errors"]
    status["quality_warnings"] = quality["warnings"]
    (site / "quality.json").write_text(json.dumps(quality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    page = site / "index.html"
    content = page.read_text(encoding="utf-8")
    problems = ", ".join(quality["critical_errors"] + quality["warnings"]) or "未偵測到結構異常（不代表已驗證賽事準確）"
    extra = ('<section id="quality-audit"><h2>資料品質與來源透明度</h2>'
             '<p>狀態：<b>' + html.escape(quality["status"]) + '</b>｜可用公開來源：'
             + str(quality["sources_usable"]) + '/' + str(quality["source_count"])
             + '｜具明確開賽時間：' + str(quality["matches_with_precise_kickoff"])
             + '/' + str(quality["public_matches"]) + '</p><p class="small">檢查：'
             + html.escape(problems) + '。下載成功不代表獨立核實；預測推薦維持停用。</p>'
             '<p><a href="quality.json">查看資料品質檢查紀錄</a></p></section>')
    if 'id="quality-audit"' not in content:
        content = content.replace('<h2>近期賽程與賽果</h2>', extra + '<h2>近期賽程與賽果</h2>', 1)
    if quality["status"] == "HOLD":
        import re
        content = re.sub(r'(<div class="status" id="research-banner"[^>]*>).*?(</div>)',
                         r'\1HOLD：資料品質檢查未通過，請查看檢查紀錄\2', content, count=1)
    page.write_text(content, encoding="utf-8")
    return quality


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default="app/site")
    args = parser.parse_args()
    print(json.dumps(apply(args.site), ensure_ascii=False))
