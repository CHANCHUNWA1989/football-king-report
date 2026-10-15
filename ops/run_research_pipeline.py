"""安全離線批次：賽前封存 + 獨立完場結果 -> 中文研究報告。"""
import argparse
import json
from pathlib import Path

from reconcile_shadow_results import reconcile
from research_input_audit import inspect
from build_zh_hant_dashboard import build_page


def run(forecasts, results, consensus=None, summary=None, gates=None):
    audit = inspect(forecasts, results)
    score_report = reconcile(forecasts, results)
    score_report["input_audit"] = audit
    if audit["status"] == "HOLD":
        score_report["status"] = "HOLD"
        score_report["production_recommendations"] = "DISABLED"
    page = build_page(shadow=score_report, consensus=consensus,
                      summary=summary, gates=gates)
    return score_report, page


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--forecasts", required=True)
    p.add_argument("--results", required=True)
    p.add_argument("--consensus")
    p.add_argument("--summary")
    p.add_argument("--gates")
    p.add_argument("--output-dir", required=True)
    args = p.parse_args()

    def load(path):
        return json.loads(Path(path).read_text(encoding="utf-8")) if path else None

    report, page = run(load(args.forecasts), load(args.results),
                       load(args.consensus), load(args.summary), load(args.gates))
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "shadow_score.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "index.html").write_text(page, encoding="utf-8")
    print(json.dumps({"status": report["status"], "accepted": report["accepted"],
                      "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
