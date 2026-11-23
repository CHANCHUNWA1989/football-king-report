"""Sanitized, fail-closed SARIF summary for J1 research CodeQL CI.

CodeQL *job success* alone never means zero findings or reviewed findings.
Parse the actual local SARIF in the CI runner, do not upload it as a public
artifact and do not emit findings' paths, messages, code snippets or secrets.
Only high/critical findings inside the J1 market parser cause this tool to
fail; all other findings still demand authorized human security triage.
"""
import argparse
from collections import Counter
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

SEVERITIES = ("critical", "high", "medium", "low", "unrated")
CATEGORIES = ("diagnostic", "metric", "severity_scored", "other_unrated")
J1_PARSER = "ops/japan_free_market.py"
MAX_RESULTS = 50000
SAFE_RULE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_./-]{0,120}$")


def _tier(score):
    if type(score) not in (int, float, str):
        return "unrated"
    try:
        value = float(score)
    except (ValueError, OverflowError):
        return "unrated"
    if not math.isfinite(value) or value < 0 or value > 10:
        return "unrated"
    if value >= 9:
        return "critical"
    if value >= 7:
        return "high"
    if value >= 4:
        return "medium"
    return "low"


def _category(rule_id, tier):
    """Rule prefixes classify diagnostics and metrics, not real vulnerabilities.

    A missing security-severity score *never* means a diagnostic by itself.
    Unscored results outside known diagnostic/metric families still need
    human triage.
    """
    if isinstance(rule_id, str):
        if rule_id.startswith("py/diagnostics/"):
            return "diagnostic"
        if rule_id.startswith("py/summary/"):
            return "metric"
    return "severity_scored" if tier != "unrated" else "other_unrated"


def _safe_rule_id(value):
    return value if isinstance(value, str) and SAFE_RULE_ID.fullmatch(value) else "unidentified-rule"


def _j1_location(result):
    for location in result.get("locations", []):
        if not isinstance(location, dict):
            continue
        physical = location.get("physicalLocation")
        if not isinstance(physical, dict):
            continue
        artifact = physical.get("artifactLocation")
        if not isinstance(artifact, dict):
            continue
        uri = artifact.get("uri")
        if (isinstance(uri, str) and
                (uri.replace("\\", "/") == J1_PARSER or
                 uri.replace("\\", "/").endswith("/" + J1_PARSER))):
            return True
    return False


def _public_tracked_py_path(result, tracked_paths):
    """Resolve SARIF location to a known, tracked PUBLIC .py path only.

    Never expose an untrusted URI, runner absolute path, message, line
    location or data-flow details. Unknown paths remain unmapped.
    """
    if not isinstance(result, dict) or not isinstance(tracked_paths, set):
        return None
    for location in result.get("locations", []):
        if not isinstance(location, dict):
            continue
        physical = location.get("physicalLocation")
        if not isinstance(physical, dict):
            continue
        artifact = physical.get("artifactLocation")
        if not isinstance(artifact, dict):
            continue
        uri = artifact.get("uri")
        if (type(uri) is not str or len(uri) > 2048
                or any(ord(c) < 32 for c in uri)
                or "%" in uri or "?" in uri or "#" in uri):
            continue
        value = uri.replace("\\", "/")
        if ".." in value.split("/"):
            continue
        if value in tracked_paths:
            return value
        if not value.startswith("file:///"):
            continue
        candidates = [name for name in tracked_paths
                      if value.endswith("/" + name)]
        if candidates:
            return max(candidates, key=len)
    return None


def _git_tracked_public_py_paths():
    """Only filenames of Python files Git already tracks in THIS checkout."""
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        check=True, timeout=10,
    )
    paths = set()
    for value in result.stdout.decode("utf-8").split(chr(0)):
        if (value and value.endswith(".py") and len(value) <= 260
                and re.fullmatch(r"[A-Za-z0-9_./-]+", value)
                and ".." not in value.split("/")
                and not value.startswith("/")):
            paths.add(value)
    if not paths:
        raise ValueError("EMPTY_TRACKED_PYTHON_FILE_INDEX")
    return paths


def summarize_sarif(document, *, tracked_public_paths=None):
    if not isinstance(document, dict) or document.get("version") != "2.1.0":
        raise ValueError("INVALID_SARIF_VERSION")
    runs = document.get("runs")
    if not isinstance(runs, list) or not runs:
        raise ValueError("SARIF_NO_RUNS")
    all_counts = Counter()
    j1_counts = Counter()
    all_categories = Counter()
    j1_categories = Counter()
    all_rules = Counter()
    j1_rules = Counter()
    public_paths = Counter()
    public_unmapped = 0
    if tracked_public_paths is not None:
        if not isinstance(tracked_public_paths, set):
            raise ValueError("INVALID_PUBLIC_PATH_ALLOWLIST")
        tracked_public_paths = {
            value for value in tracked_public_paths
            if (type(value) is str and value.endswith(".py")
                and re.fullmatch(r"[A-Za-z0-9_./-]+", value)
                and ".." not in value.split("/")
                and not value.startswith("/"))
        }
    total = 0
    for run in runs:
        if not isinstance(run, dict):
            raise ValueError("INVALID_SARIF_RUN")
        driver = run.get("tool", {}).get("driver", {})
        if not isinstance(driver, dict):
            raise ValueError("INVALID_SARIF_DRIVER")
        rules = {}
        for rule in driver.get("rules", []):
            if not isinstance(rule, dict):
                continue
            rule_id = rule.get("id")
            props = rule.get("properties")
            if isinstance(rule_id, str) and isinstance(props, dict):
                rules[rule_id] = props.get("security-severity")
        results = run.get("results")
        if not isinstance(results, list):
            raise ValueError("INVALID_SARIF_RESULTS")
        total += len(results)
        if total > MAX_RESULTS:
            raise ValueError("SARIF_RESULT_LIMIT")
        for item in results:
            if not isinstance(item, dict):
                raise ValueError("INVALID_SARIF_FINDING")
            rule_id = item.get("ruleId")
            props = item.get("properties")
            score = props.get("security-severity") if isinstance(props, dict) else None
            if score is None:
                score = rules.get(rule_id)
            tier = _tier(score)
            category = _category(rule_id, tier)
            safe_id = _safe_rule_id(rule_id)
            all_counts[tier] += 1
            all_categories[category] += 1
            all_rules[(safe_id, category)] += 1
            if tracked_public_paths is not None:
                public = _public_tracked_py_path(item, tracked_public_paths)
                if public is None:
                    public_unmapped += 1
                else:
                    public_paths[public] += 1
            if _j1_location(item):
                j1_counts[tier] += 1
                j1_categories[category] += 1
                j1_rules[safe_id] += 1
    summary = {
        "format": "j1-codeql-sarif-summary-v1",
        "run_count": len(runs),
        "all_finding_count": total,
        "all_by_severity": {key: all_counts[key] for key in SEVERITIES},
        "all_by_category": {key: all_categories[key] for key in CATEGORIES},
        "all_rule_ids_top20": [
            {"rule_id": rule, "count": count, "category": category}
            for (rule, category), count in sorted(
                all_rules.items(),
                key=lambda x: (-x[1], x[0][0], x[0][1])
            )[:20]
        ],
        "j1_parser_finding_count": sum(j1_counts.values()),
        "j1_parser_by_severity": {key: j1_counts[key] for key in SEVERITIES},
        "j1_parser_by_category": {key: j1_categories[key] for key in CATEGORIES},
        "j1_parser_high_critical_gate": (
            "FAIL" if j1_counts["high"] + j1_counts["critical"] else "PASS"
        ),
        # A J1 parser result without a numeric security-severity is not
        # automatically safe. Only known CodeQL diagnostic/metric families
        # are excluded from the unscored-review blocking condition.
        "j1_parser_security_review_gate": (
            "FAIL" if (j1_counts["high"] + j1_counts["critical"]
                       + j1_categories["other_unrated"]) else "PASS"
        ),
        "j1_rule_ids_top10": [
            {"rule_id": key, "count": amount}
            for key, amount in sorted(j1_rules.items(), key=lambda x: (-x[1], x[0]))[:10]
        ],
        "human_review_required": True,
        "source_quote_or_model_authentication": False,
    }
    if tracked_public_paths is not None:
        summary["public_tracked_python_paths_top20"] = [
            {"path": filename, "count": amount}
            for filename, amount in sorted(
                public_paths.items(), key=lambda x: (-x[1], x[0])
            )[:20]
        ]
        summary["unmapped_public_location_count"] = public_unmapped
        summary["public_path_metadata_only"] = True
    return summary


def _markdown(summary):
    lines = [
        "### J1 research CodeQL — local SARIF finding summary",
        "",
        "This is a **scan-result summary**, not a human review or a guarantee of no vulnerabilities.",
        "Counts reflect this SARIF run, **not** the number of open GitHub Security alerts.",
        "",
        "| Finding severity | Whole repository | J1 market parser |",
        "| --- | ---: | ---: |",
    ]
    for severity in SEVERITIES:
        lines.append(
            f"| {severity} | {summary['all_by_severity'][severity]} | "
            f"{summary['j1_parser_by_severity'][severity]} |"
        )
    lines.extend([
        "",
        "| CodeQL result category | Whole repository | J1 market parser |",
        "| --- | ---: | ---: |",
    ])
    for category in CATEGORIES:
        lines.append(
            f"| {category} | {summary['all_by_category'][category]} | "
            f"{summary['j1_parser_by_category'][category]} |"
        )
    lines.extend([
        "",
        f"**J1 parser high/critical gate:** {summary['j1_parser_high_critical_gate']}",
        f"**J1 parser security-review gate (including unscored non-diagnostic results):** "
        f"{summary['j1_parser_security_review_gate']}",
        "",
        "All findings still need GitHub Security alert review and independent code review. "
        "No data-vendor rights, executable odds, prospective samples or positive EV are certified.",
    ])
    if summary["all_rule_ids_top20"]:
        lines.extend([
            "",
            "**Repository rule IDs (top 20, sanitized, metadata only):**",
        ])
        for item in summary["all_rule_ids_top20"]:
            lines.append(
                f"- `{item['rule_id']}` ({item['category']}): {item['count']}"
            )
    if "public_tracked_python_paths_top20" in summary:
        lines.extend([
            "",
            "**Public Git-tracked Python files referenced by SARIF (top 20):**",
            "",
            "Repository-relative public filenames only; no source snippets, "
            "raw URLs, line numbers, tokens, or vulnerability claims.",
        ])
        for item in summary["public_tracked_python_paths_top20"]:
            lines.append(f"- `{item['path']}`: {item['count']}")
        lines.append(
            f"- Unmapped SARIF results: {summary['unmapped_public_location_count']}"
        )
    if summary["j1_rule_ids_top10"]:
        lines.extend(["", "**J1 parser rule IDs (top 10, sanitized):**"])
        for item in summary["j1_rule_ids_top10"]:
            lines.append(f"- `{item['rule_id']}`: {item['count']}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--public-tracked-python-paths", action="store_true")
    args = parser.parse_args(argv)
    try:
        tracked = None
        if args.public_tracked_python_paths:
            if os.environ.get("FK_PUBLIC_REPOSITORY") != "true":
                raise ValueError("PUBLIC_PATH_REPORTING_REQUIRES_PUBLIC_REPOSITORY")
            tracked = _git_tracked_public_py_paths()
        files = sorted(args.directory.glob("*.sarif"))
        if not files:
            raise ValueError("SARIF_MISSING")
        merged = []
        for path in files:
            if path.stat().st_size > 50_000_000:
                raise ValueError("SARIF_OVERSIZE")
            with path.open(encoding="utf-8") as handle:
                document = json.load(handle)
            if not isinstance(document, dict) or not isinstance(document.get("runs"), list):
                raise ValueError("INVALID_SARIF")
            merged.extend(document["runs"])
        summary = summarize_sarif(
            {"version": "2.1.0", "runs": merged},
            tracked_public_paths=tracked,
        )
        print("J1_CODEQL_SUMMARY=" + json.dumps(summary, sort_keys=True, separators=(",", ":")))
        step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if step_summary:
            with open(step_summary, "a", encoding="utf-8") as output:
                output.write(_markdown(summary))
        return 2 if summary["j1_parser_security_review_gate"] == "FAIL" else 0
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError,
            subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        # Only an error category, never the potentially sensitive contents of
        # a SARIF or a runner-local path, may go to public CI logs.
        print("J1_CODEQL_SUMMARY_ERROR=" + type(exc).__name__)
        return 3


if __name__ == "__main__":
    sys.exit(main())
