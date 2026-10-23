"""Fail-closed, same-fixture market-competitiveness audit (RESEARCH ONLY).

No odds scraping, probabilistic recalibration, or in-play prediction.
This is a *diagnostic*, never proof of profitable bets. In particular,
the current public settled-result metadata is NOT independently attested.
"""
import argparse
import html
import json
from pathlib import Path

from model_market_bias_audit import audit as paired_audit

SCHEMA = "football-king-competitive-guard-v1"
MIN_DIAGNOSTIC_CASES = 20  # Alert threshold, NOT a significance claim.
MIN_VALIDATION_CASES = 300
MARKET_TRAILING_REASON = "MARKET_BETTER_ON_BOTH_SCORES_UNVERIFIED"
NON_VETO_REASONS = (
    "NOT_ENOUGH_DIAGNOSTIC_CASES", "INSUFFICIENT_FORWARD_VALIDATION",
    "INDEPENDENT_RESULT_AND_PRICE_EVIDENCE_REQUIRED",
)


def build(evidence):
    """Only sealed same-case model/market vectors; reject invalid chronology."""
    if (not isinstance(evidence, dict)
            or evidence.get("schema") != "football-king-forward-research-1"
            or evidence.get("production_recommendations") != "DISABLED"
            or not isinstance(evidence.get("samples"), list)
            or type(evidence.get("n")) is not int
            or evidence["n"] != len(evidence["samples"])
            or not isinstance(evidence.get("checked_utc"), str)):
        raise ValueError("INVALID_FORWARD_EVIDENCE")
    source = paired_audit(
        evidence["samples"], archived_at_utc=evidence["checked_utc"])
    d = source["diagnostics"]
    n = len(evidence["samples"])
    model_worse = bool(
        d is not None and n >= MIN_DIAGNOSTIC_CASES
        and d["model_log_loss"] > d["market_log_loss"]
        and d["model_brier"] > d["market_brier"])
    if model_worse:
        reason = MARKET_TRAILING_REASON
    elif n < MIN_DIAGNOSTIC_CASES:
        reason = "NOT_ENOUGH_DIAGNOSTIC_CASES"
    elif n < MIN_VALIDATION_CASES:
        reason = "INSUFFICIENT_FORWARD_VALIDATION"
    else:
        reason = "INDEPENDENT_RESULT_AND_PRICE_EVIDENCE_REQUIRED"
    # Source attestation cannot be inferred from metadata, even if flags on
    # individual fixtures claim they are independently verified.
    comparison = None
    if d is not None:
        comparison = {
            "sample_count": n,
            "model_log_loss": d["model_log_loss"],
            "market_log_loss": d["market_log_loss"],
            "model_brier": d["model_brier"],
            "market_brier": d["market_brier"],
            "model_correct": d["model_top_choice_correct"],
            "market_correct": d["market_top_choice_correct"],
            "model_home_top_count": d["model_home_top_count"],
            "market_home_top_count": d["market_home_top_count"],
            "actual_home_wins_count": d["actual_home_wins_count"],
            "model_home_top_fraction": round(d["model_home_top_count"] / n, 6),
            "market_home_top_fraction": round(d["market_home_top_count"] / n, 6),
            "actual_home_win_fraction": d["actual_home_win_fraction"],
            "model_minus_market_home_top_pp": round(
                100 * (d["model_home_top_count"] - d["market_home_top_count"]) / n, 2),
            "model_minus_market_log_loss": round(
                d["model_log_loss"] - d["market_log_loss"], 6),
            "model_minus_market_brier": round(
                d["model_brier"] - d["market_brier"], 6),
            "independent_week_blocks": d["independent_week_blocks"],
            "per_league_samples": d["league_case_counts"],
            "week_block_bootstrap_95pct_ci": d["paired_week_block_bootstrap_95pct_ci"],
        }
    return {
        "schema": SCHEMA, "as_of_utc": evidence["checked_utc"],
        "status": "HOLD", "reason": reason,
        "paired_same_fixture_count": n,
        "model_currently_behind_market_on_both_scores": model_worse,
        "primary_shortlist_veto": model_worse,
        "primary_shortlist_veto_is_not_model_retraining": True,
        "comparison": comparison,
        "sample_threshold_met": n >= MIN_VALIDATION_CASES,
        "independent_result_authentication": False,
        "calibration_verified": False,
        "market_prices_executable": False,
        "out_of_sample_market_superiority_proven": False,
        "betting_ev_verified": False,
        "automatic_bets": False,
        "recommended_bets": [],
        "production_recommendations": "DISABLED",
        "warning_zh": (
            "只用同場封存預測與市場比較；賽果來源未獨立認證。"
            "即使市場勝出亦屬小樣本描述，不能證明盈利能力。"
        ),
    }


def enforce_shortlist(result, report):
    """Prevent a clearly trailing shadow model being framed as 'top picks'.

    Preserves the raw sealed forecasts outside this view for unbiased future
    testing. Does not modify market odds, model probabilities or archived rows.
    """
    if not isinstance(result, dict):
        raise ValueError("INVALID_SHORTLIST")
    # Missing, malformed, or inconsistent decision metadata: fail closed.
    # Shape/consistency checks do not authenticate the underlying evidence.
    valid = (isinstance(report, dict)
             and report.get("schema") == SCHEMA
             and report.get("production_recommendations") == "DISABLED"
             and report.get("out_of_sample_market_superiority_proven") is False
             and report.get("betting_ev_verified") is False
             and report.get("status") == "HOLD"
             and type(report.get("primary_shortlist_veto")) is bool
             and type(report.get("model_currently_behind_market_on_both_scores")) is bool
             and report["primary_shortlist_veto"] is
                 report["model_currently_behind_market_on_both_scores"]
             and type(report.get("reason")) is str
             and report["reason"] in (
                 (MARKET_TRAILING_REASON,) if report["primary_shortlist_veto"]
                 else NON_VETO_REASONS))
    blocked = (not valid or report.get("primary_shortlist_veto") is True)
    result["competitive_guard_status"] = (
        report.get("reason") if valid else "MISSING_OR_INVALID_COMPETITIVE_EVIDENCE")
    result["competitive_market_outperformance_proven"] = False
    if not blocked:
        result["competitive_suppressed_count"] = 0
        return result
    removed = (len(result.get("selections", []))
               + len(result.get("reviews", []))
               + len(result.get("model_only_watchlist", [])))
    result["selections"] = []
    result["selected_count"] = 0
    result["reviews"] = []
    result["review_count"] = 0
    result["model_only_watchlist"] = []
    result["model_only_count"] = 0
    result["fallback_mode"] = "NOT_NEEDED"
    result["fallback_reason"] = "COMPETITIVE_MODEL_GATE_BLOCKED"
    result["reason"] = "COMPETITIVE_EVIDENCE_HOLD"
    result["status"] = "HOLD"
    result["competitive_suppressed_count"] = removed
    if isinstance(result.get("diagnostics"), dict):
        result["diagnostics"]["research_shortlisted"] = 0
        result["diagnostics"]["model_only_watchlist"] = 0
        result["diagnostics"]["competitive_guard_veto"] = True
        result["diagnostics"]["no_output_explanation"] = (
            "Market comparison failed or unverifiable; archived forecasts remain in Shadow Mode.")
    return result


def publish(site, ledger):
    site = Path(site)
    evidence = json.loads(Path(ledger).read_text(encoding="utf-8"))
    report = build(evidence)
    (site / "competitive_guard.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def render(site):
    """Static iPhone disclosure; never inserts untrusted team/market strings."""
    site = Path(site)
    report = json.loads((site / "competitive_guard.json").read_text(encoding="utf-8"))
    if (report.get("schema") != SCHEMA
            or report.get("production_recommendations") != "DISABLED"
            or report.get("status") != "HOLD"):
        raise ValueError("INVALID_COMPETITIVE_GUARD_FOR_PUBLICATION")
    c = report.get("comparison")
    if c is None:
        summary = "暫無符合時間點要求嘅已結算模型／市場配對樣本。"
    else:
        n = c["sample_count"]
        summary = (
            f"封存同場樣本 {n} 場；模型首選 {c['model_correct']}/{n}，"
            f"市場首選 {c['market_correct']}/{n}；"
            f"模型主勝首選 {c['model_home_top_count']}/{n}。"
        )
    if report.get("primary_shortlist_veto"):
        status = "暫停突出研究首選：現有小樣本中市場 Log Loss 與 Brier 均較優。"
    else:
        status = "模型尚未證明能超越市場，正式下注建議維持停用。"
    panel = (
        '<section id="fk-competitive-guard" role="status" '
        'style="padding:12px;border:1px solid #64748b;border-radius:12px;margin:16px 0">'
        '<h2>模型對市場競爭力實測｜HOLD</h2>'
        '<p>' + html.escape(summary) + '</p>'
        '<p>' + html.escape(status) + '</p>'
        '<p>所有比率只屬未獨立認證樣本描述，並非可下注勝率。'
        '無合法可執行價格、校準及前瞻證據，絕不自動下注。</p>'
        '<p><a href="competitive_guard.json">查看同場比較及主勝偏差報告</a></p>'
        '</section>'
    )
    page = site / "index.html"
    source = page.read_text(encoding="utf-8")
    if 'id="fk-competitive-guard"' in source:
        raise ValueError("DUPLICATE_COMPETITIVE_GUARD_PANEL")
    if '<h2>近期賽程與賽果</h2>' in source:
        source = source.replace('<h2>近期賽程與賽果</h2>',
                                panel + '<h2>近期賽程與賽果</h2>', 1)
    elif "</body>" in source:
        source = source.replace("</body>", panel + "</body>", 1)
    else:
        raise ValueError("MISSING_HTML_INSERTION_POINT")
    page.write_text(source, encoding="utf-8")
    return {"competitive_guard_visible": True, "production_recommendations": "DISABLED"}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--site", default="app/site")
    p.add_argument("--evidence", default="settled-next.json")
    p.add_argument("--render", action="store_true")
    a = p.parse_args()
    report = render(a.site) if a.render else publish(a.site, a.evidence)
    print(json.dumps(report, ensure_ascii=False))
