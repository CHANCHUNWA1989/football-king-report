"""Single-command offline provider export -> research JSON + Cantonese Markdown.

Usage:
 python -m ops.provider_research_cli --input export.json --output report.json --markdown report.md
The input is an external, documented export, NOT automatically downloaded odds.
"""
import argparse
import json
from pathlib import Path
from ops.offline_provider_export import adapt_export
from ops.daily_research_report import build_daily_research_report
from ops.daily_research_markdown import render_markdown

def run(input_path, output_path, markdown_path, *, generated_utc):
    source, output, markdown = map(Path, (input_path, output_path, markdown_path))
    if len({p.resolve() for p in (source, output, markdown)}) != 3:
        raise ValueError("INPUT_OUTPUT_PATH_COLLISION")
    export = json.loads(source.read_text(encoding="utf-8"))
    payload = adapt_export(export, generated_utc=generated_utc)
    report = build_daily_research_report(payload["rows"], generated_utc=payload["generated_utc"])
    if report.get("production_recommendations") != "HOLD" or report.get("positive_ev_verified") is not False:
        raise ValueError("UNSAFE_REPORT")
    rendered = render_markdown(report)
    json_output = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json_output, encoding="utf-8")
    markdown.write_text(rendered + "\n", encoding="utf-8")
    return report

def main():
    parser = argparse.ArgumentParser(description="Offline football research only; betting HOLD")
    parser.add_argument("--input", required=True, help="Documented provider export JSON")
    parser.add_argument("--output", required=True, help="Research JSON report")
    parser.add_argument("--markdown", required=True, help="Cantonese Markdown report")
    parser.add_argument("--generated-utc", required=True, help="Aware ISO 8601 snapshot timestamp")
    args = parser.parse_args()
    report = run(args.input, args.output, args.markdown, generated_utc=args.generated_utc)
    print(f"Research only; fixtures={report['sample_count']}; betting HOLD")

if __name__ == "__main__":
    main()
