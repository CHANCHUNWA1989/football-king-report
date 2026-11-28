"""Standalone mobile research report. No deployment or source authentication."""
from collections import Counter
from math import isfinite
from ops.model_divergence_batch import MAX_FIXTURES

LABELS = {
    "DIRECTION_CONFLICT": "模型預測方向衝突",
    "LARGE_GAP": "模型概率差距過大",
    "NO_LARGE_DISAGREEMENT": "未觸發分歧閾值",
    "MISSING_PAIR": "缺少模型配對",
    "INVALID_INPUT": "身份、時間或概率資料不合格",
}
FALSE_FLAGS = ("source_authenticated", "native_identity_authenticated",
               "source_bytes_verified", "model_input_derivation_verified",
               "model_calibrated", "can_recommend_bets")


def summarize(report):
    """Validate only a declared report's internal structure, not its origin."""
    out = dict(status="HOLD", production_recommendations="DISABLED",
               can_recommend_bets=False, source_authenticated=False,
               input_report_valid=False, reported_count=0, counts={})
    try:
        if type(report) is not dict or report.get("production_recommendations") != "DISABLED":
            return out
        if any(report.get(k) is not False for k in FALSE_FLAGS):
            return out
        if report.get("normalized_documents_hash_match") is not True:
            return out
        rows = report["results"]
        if type(rows) is not list or not 1 <= len(rows) <= MAX_FIXTURES:
            return out
        counts = Counter()
        for i, row in enumerate(rows):
            if type(row) is not dict or type(row.get("manifest_index")) is not int or row["manifest_index"] != i:
                return out
            reason = row["reason"]
            if type(reason) is not str or reason not in LABELS:
                return out
            expected = "RESEARCH_ONLY" if reason == "NO_LARGE_DISAGREEMENT" else "HOLD"
            if row["status"] != expected:
                return out
            gap = row["max_gap"]
            if reason in ("MISSING_PAIR", "INVALID_INPUT"):
                if gap is not None:
                    return out
            elif type(gap) not in (float, int) or not 0 <= gap <= 1 or not isfinite(gap):
                return out
            elif reason == "LARGE_GAP" and gap < 0.10 - 1e-12:
                return out
            elif reason == "NO_LARGE_DISAGREEMENT" and gap >= 0.10 - 1e-12:
                return out
            counts[reason] += 1
        declared = report["counts"]
        if type(declared) is not dict or any(type(v) is not int for v in declared.values()) or declared != dict(counts):
            return out
        all_clear = counts["NO_LARGE_DISAGREEMENT"] == len(rows)
        if report.get("status") != ("RESEARCH_ONLY" if all_clear else "HOLD"):
            return out
        if report.get("reason") != ("COMPLETE_RESEARCH_COMPARISON" if all_clear else "PAIR_HOLD"):
            return out
    except (KeyError, TypeError, ValueError, OverflowError):
        return out
    return {**out, "input_report_valid": True, "reported_count": len(rows),
            "counts": dict(counts)}


def render(report):
    """Render fixed Chinese labels and bounded integer counts, never raw text."""
    summary = summarize(report)
    body = "<p>未有合格報告，禁止升級。</p>"
    if summary["input_report_valid"]:
        items = "".join("<li>" + LABELS[k] + "：" + str(summary["counts"].get(k, 0)) + "</li>"
                        for k in LABELS)
        body = "<p>輸入報告聲稱比較場數：" + str(summary["reported_count"]) + "</p><ul>" + items + "</ul>"
    return ("<!doctype html><html lang='zh-Hant-HK'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'\">"
            "<title>足球王者｜模型分歧研究</title>"
            "<style>body{font:17px system-ui,sans-serif;margin:1rem;line-height:1.6;"
            "background:#f7f8fa;color:#15212a}main{max-width:42rem;margin:auto}"
            "h1{font-size:1.5rem}.warning{border:2px solid #936000;padding:1rem;"
            "border-radius:.5rem;background:#fff7e5}li{margin:.4rem 0}"
            "@media(prefers-color-scheme:dark){body{background:#15191f;color:#eee}"
            ".warning{background:#33260f;color:#fff}}</style></head><body><main>"
            "<h1>足球王者｜模型分歧研究</h1><section class='warning' role='status'>"
            "<strong>HOLD／DISABLED</strong><p>只供研究；不可作正式投注依據。</p></section>"
            "<p>離線報告，非即時數據。來源、時間、模型校準及推導未獲獨立認證。</p>"
            + body + "<p>未觸發閾值不代表預測可靠或具有正期望值。</p></main></body></html>")
