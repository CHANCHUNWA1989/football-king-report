"""將現有機器報告輸出成手機可讀繁體中文靜態頁面（不連網）。"""
import argparse
import html
import json
import math
from datetime import datetime, timezone
from pathlib import Path

if __package__:
    from .report_zh_hant import readiness_zh, shadow_zh, market_audit_zh
    from .recommendation_readiness import EXPECTED_GATE_KEYS, quality_gate_states
else:
    from report_zh_hant import readiness_zh, shadow_zh, market_audit_zh
    from recommendation_readiness import EXPECTED_GATE_KEYS, quality_gate_states


def render_section(title, report):
    rows = []
    for key, value in report.items():
        if key in ("報告", "提示"):
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, indent=2)
        elif value is None:
            value = "暫無數據"
        rows.append(f"<dt>{html.escape(str(key))}</dt><dd>{html.escape(str(value))}</dd>")
    return (f"<section><h2>{html.escape(title)}</h2><dl>"
            + "".join(rows) + "</dl><p class='note'>"
            + html.escape(report.get("提示", "")) + "</p></section>")


def _valid_probability(value):
    return (type(value) in (int, float) and 0 <= value <= 1
            and math.isfinite(value))


def _safe_case_goal_scoring(report):
    """Return display-only data after checking the replay's fail-closed contract."""
    if type(report) is not dict or report.get("schema") != "football-king-controlled-case-replay-v1":
        return None
    if (report.get("status") != "HOLD"
            or report.get("production_recommendations") != "DISABLED"
            or report.get("replay_completed") is not True
            or report.get("candidate_only") is not True
            or report.get("derived_review_not_a_trust_input") is not True
            or report.get("goal_market_replay_completed") is not True):
        return None
    scoring = report.get("goal_market_scoring")
    if type(scoring) is not dict or scoring.get("schema") != "football-king-case-goal-market-reconstruction-v1":
        return None
    if (scoring.get("status") != "HOLD"
            or scoring.get("production_recommendations") != "DISABLED"
            or scoring.get("candidate_only") is not True
            or scoring.get("derived_reconstruction") is not True
            or scoring.get("derived_review_not_a_trust_input") is not True
            or type(scoring.get("certified_case_count")) is not int
            or scoring.get("certified_case_count") != 0):
        return None
    for key in ("distribution_sealed_pre_match", "independently_verified",
                "eligible_for_model_scoring", "eligible_for_betting_promotion",
                "results_independently_verified", "offered_handicap_line_authenticated",
                "offered_totals_line_authenticated", "offered_decimal_odds_authenticated",
                "probability_calibration_verified", "positive_expected_value_verified"):
        if scoring.get(key) is not False:
            return None

    btts = scoring.get("both_teams_to_score")
    scores = scoring.get("correct_score_diagnostic")
    markets = scoring.get("result_market_diagnostics")
    children = (btts, scores, markets)
    if any(type(child) is not dict or child.get("status") != "HOLD"
           or child.get("production_recommendations") != "DISABLED"
           or child.get("basis") != "DERIVED_INDEPENDENT_POISSON_GRID"
           for child in children):
        return None
    for child in children:
        for key in ("forecast_sealed_pre_match", "offered_market_authenticated",
                    "calibration_verified", "results_independently_verified",
                    "positive_ev_verified"):
            if child.get(key) is not False:
                return None

    btts_probs = btts.get("probabilities")
    if (type(btts_probs) is not dict or set(btts_probs) != {"YES", "NO"}
            or not all(_valid_probability(x) for x in btts_probs.values())
            or not math.isclose(math.fsum(btts_probs.values()), 1.0, abs_tol=1e-9)):
        return None

    rows = scores.get("top_scorelines")
    if type(rows) is not list or len(rows) != 5 or scores.get("top_k") != 5:
        return None
    clean_rows = []
    seen = set()
    for row in rows:
        if type(row) is not dict:
            return None
        home, away, probability = row.get("home_goals"), row.get("away_goals"), row.get("probability")
        if (type(home) is not int or home < 0 or type(away) is not int or away < 0
                or not _valid_probability(probability) or (home, away) in seen):
            return None
        seen.add((home, away))
        clean_rows.append((home, away, probability))
    ranked = sorted(clean_rows, key=lambda row: (-row[2], row[0], row[1]))
    if clean_rows != ranked:
        return None
    top_mass = scores.get("top_scorelines_probability_mass")
    remaining = scores.get("other_in_grid_probability_mass")
    if (not _valid_probability(top_mass) or not _valid_probability(remaining)
            or not math.isclose(math.fsum(row[2] for row in clean_rows), top_mass, abs_tol=1e-8)
            or not math.isclose(top_mass + remaining, 1.0, abs_tol=1e-8)):
        return None

    double = markets.get("double_chance")
    if (type(double) is not dict or set(double) != {"1X", "X2", "12"}
            or not all(_valid_probability(x) for x in double.values())
            or markets.get("double_chance_markets_overlap") is not True
            or not math.isclose(math.fsum(double.values()), 2.0, abs_tol=1e-9)):
        return None
    dnb = markets.get("draw_no_bet")
    if type(dnb) is not dict or set(dnb) != {"HOME", "AWAY"}:
        return None
    for side in ("HOME", "AWAY"):
        item = dnb.get(side)
        if type(item) is not dict:
            return None
        full_win, push, full_loss = (item.get("full_win_probability"),
                                     item.get("push_probability"),
                                     item.get("full_loss_probability"))
        conditional = item.get("conditional_win_probability_given_no_push")
        if (not all(_valid_probability(x) for x in (full_win, push, full_loss))
                or not math.isclose(math.fsum((full_win, push, full_loss)), 1.0, abs_tol=1e-9)):
            return None
        non_push = full_win + full_loss
        if non_push == 0:
            if conditional is not None:
                return None
        elif (not _valid_probability(conditional)
              or not math.isclose(conditional, full_win / non_push, abs_tol=1e-9)):
            return None
    return {"btts": btts_probs, "scores": clean_rows, "top_mass": top_mass,
            "remaining": remaining, "double_chance": double, "dnb": dnb}


def case_replay_section(report):
    data = _safe_case_goal_scoring(report)
    if data is None:
        return ("<section class='research'><h2>衍生研究概率</h2>"
                "<p class='note'>研究概率資料未能通過格式及安全驗證；本頁不顯示概率。"
                "正式推薦：HOLD／DISABLED。</p></section>")

    def percent(value):
        return f"{value * 100:.1f}%"

    def bar(label, value):
        shown = percent(value)
        return (f"<div class='prob-row'><div><span>{html.escape(label)}</span>"
                f"<strong>{shown}</strong></div><div class='progress'>"
                f"<div class='progress-bar' role='progressbar' aria-label='{html.escape(label)}' "
                f"aria-valuemin='0' aria-valuemax='100' aria-valuenow='{value * 100:.4f}' "
                f"style='width:{value * 100:.4f}%'></div></div></div>")

    cards = ["<article class='metric-card'><h3>雙方入球</h3>"]
    cards.append(bar("YES", data["btts"]["YES"]))
    cards.append(bar("NO", data["btts"]["NO"]))
    cards.append("</article><article class='metric-card'><h3>候選比分 Top 5</h3>")
    for home, away, probability in data["scores"]:
        cards.append(bar(f"{home}–{away}", probability))
    cards.append(f"<p>Top 5 概率質量：{percent(data['top_mass'])}</p>"
                 f"<p>其餘保留比分格：{percent(data['remaining'])}</p></article>")
    cards.append("<article class='metric-card'><h3>雙重機會（互相重疊）</h3>"
                 "<p class='note'>重疊概率總和為 2</p>")
    for label in ("1X", "X2", "12"):
        cards.append(bar(label, data["double_chance"][label]))
    cards.append("</article><article class='metric-card'><h3>和局退款（DNB）</h3>")
    for side, label in (("HOME", "主隊"), ("AWAY", "客隊")):
        item = data["dnb"][side]
        cards.append(f"<h4>{label}</h4>")
        cards.append(bar("全贏", item["full_win_probability"]))
        cards.append(bar("走盤", item["push_probability"]))
        cards.append(bar("全輸", item["full_loss_probability"]))
        conditional = item["conditional_win_probability_given_no_push"]
        cards.append(f"<p>排除走盤後勝率：{'未定義' if conditional is None else percent(conditional)}</p>")
    cards.append("</article>")
    return ("<section class='research'><h2>衍生研究概率</h2>"
            "<p><strong>正式推薦：HOLD／DISABLED</strong></p><div class='metric-grid'>"
            + "".join(cards) + "</div><p class='note'>由候選個案的截斷 Poisson 格衍生；"
            "非賽前封存、非可成交報價、未校準、未獨立核實，亦非 EV。</p></section>")


def existing_sources_zh(consensus=None, summary=None, gates=None):
    consensus, summary, gates = consensus or {}, summary or {}, gates or {}
    progress = summary.get("evidence_progress") or {}
    quota = consensus.get("quota") or {}
    checks = quality_gate_states(gates)
    passed = sum(state == "PASS" for state in checks.values())
    markets = consensus.get("requested_markets") or [consensus.get("market", "未知")]
    timestamp = consensus.get("as_of_utc")
    freshness = "未知（沒有有效快照時間）"
    if isinstance(timestamp, str):
        try:
            captured = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if captured.tzinfo is not None:
                hours = (datetime.now(timezone.utc) - captured).total_seconds() / 3600
                if hours < -0.083333:
                    freshness = "異常：快照時間晚於現在"
                elif hours > 24:
                    freshness = "過期：超過24小時"
                else:
                    freshness = "24小時內快照（不代表即時盤口）"
        except ValueError:
            pass
    return {
        "報告": "足球王者｜現有研究快照",
        "資料時效": freshness,
        "盤口快照時間（UTC）": consensus.get("as_of_utc"),
        "市場賽事數量": consensus.get("event_count"),
        "已請求市場": "、".join(str(x) for x in markets),
        "免費額度餘額（快照）": quota.get("remaining"),
        "封存結算候選個案": progress.get("settled_cases_in_archive"),
        "結算個案目標": progress.get("settled_cases_required"),
        "獨立核實賽果": progress.get("independently_verified_result_cases"),
        "七項品質關卡通過": str(passed) + "/" + str(len(EXPECTED_GATE_KEYS)),
        "未通過關卡": [key for key, state in checks.items() if state != "PASS"],
        "正式推薦": "未開放",
        "提示": "以上只係儲存庫內快照，可能過期；市場共識並非獨立模型預測。",
    }


def build_page(readiness=None, shadow=None, market=None, consensus=None, summary=None, gates=None,
               case_replay=None):
    sections = [
        render_section("現有數據及驗收進度", existing_sources_zh(consensus, summary, gates)),
        render_section("正式推薦驗收", readiness_zh(readiness or {})),
        render_section("獨贏盤賽後覆盤", shadow_zh(shadow or {})),
        render_section("三市場盤口品質", market_audit_zh(market or {})),
    ]
    if case_replay is not None:
        sections.append(case_replay_section(case_replay))
    return """<!doctype html>
<html lang="zh-Hant-HK"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>足球王者｜研究報告</title>
<style>
:root{color-scheme:light dark;font-family:system-ui,-apple-system,sans-serif}
body{max-width:860px;margin:auto;padding:18px;line-height:1.65}
header{border-bottom:2px solid #888;padding-bottom:12px}
section{border:1px solid #8886;border-radius:12px;padding:16px;margin:18px 0}
article.metric-card{border:1px solid #8886;border-radius:10px;padding:14px;min-width:0}
.metric-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:12px}
.prob-row{margin:10px 0}.prob-row>div:first-child{display:flex;justify-content:space-between;gap:12px}
.progress{height:9px;margin-top:5px;overflow:hidden;border-radius:999px;background:#8885}
.progress-bar{height:100%;border-radius:inherit;background:#2878c7}
dl{display:grid;grid-template-columns:minmax(120px,1fr) 2fr;gap:9px}
dt{font-weight:700}dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}
.note{opacity:.85}strong{font-weight:800}
@media(max-width:550px){dl{grid-template-columns:1fr}dd{padding-bottom:8px}}
</style></head><body><header><h1>足球王者｜繁體中文研究報告</h1>
<p><strong>正式推薦：未開放</strong> · 僅供研究，並非投注建議</p></header>
""" + "".join(sections) + "</body></html>"


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--readiness")
    p.add_argument("--shadow")
    p.add_argument("--market")
    p.add_argument("--consensus")
    p.add_argument("--summary")
    p.add_argument("--gates")
    p.add_argument("--case-replay", help="受控個案重播 JSON（只顯示衍生研究資料）")
    p.add_argument("--output", required=True)
    args = p.parse_args(argv)
    output = Path(args.output)
    if args.case_replay and Path(args.case_replay).resolve() == output.resolve():
        p.error("--output must not overwrite the --case-replay source")

    def read(path):
        return json.loads(Path(path).read_text(encoding="utf-8")) if path else None

    output.parent.mkdir(parents=True, exist_ok=True)
    case_replay = read(args.case_replay)
    output.write_text(build_page(read(args.readiness), read(args.shadow),
                                 read(args.market), read(args.consensus),
                                 read(args.summary), read(args.gates), case_replay), encoding="utf-8")
    print(json.dumps({"status": "GENERATED", "output": str(output),
                      "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
