"""Prepare a safe, offline handoff for ChatGPT Work / Codex from the existing audit.

No model calls, paid APIs, credentials, betting actions or repository writes.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

_COMPONENTS = frozenset({
    "ops/research_recommender.py", "ops/forward_validation.py",
    "ops/release_guard.py", "market/latest.json",
    "sources/latest.json", "evidence/settled.json",
})
_REASONS = frozenset({
    "MISSING", "MISSING_COMPONENT", "OVERSIZED", "INVALID_OBJECT",
    "UNSAFE_PRODUCTION_FLAG", "MISSING_TIMESTAMP", "NAIVE_TIMESTAMP",
    "FUTURE_TIMESTAMP", "STALE", "SOURCE_NOT_READY",
    "EMPTY_MARKET_COVERAGE", "NO_MARKET_EVENTS", "EMPTY_SOURCE_COVERAGE",
    "SETTLEMENT_OLDER_THAN_48H", "INVALID_EVIDENCE",
    "INVALID_EVIDENCE_TIME", "OVERSIZED_EVIDENCE",
})


def render(audit):
    """Accept only a validated v2 shadow audit, and never echo untrusted text."""
    if not isinstance(audit, dict) or any((
        audit.get("schema") != "football-king-agent-audit-v2",
        audit.get("mode") != "SHADOW_READ_ONLY",
        audit.get("production_recommendations") != "DISABLED",
        audit.get("automatic_bets") is not False,
        audit.get("actions_performed") != [],
    )):
        raise ValueError("UNSAFE_OR_UNKNOWN_AGENT_AUDIT")
    status = audit.get("status")
    if status not in ("HOLD", "READY_FOR_MANUAL_REVIEW"):
        raise ValueError("UNKNOWN_AUDIT_STATUS")
    next_action = ("REFRESH_OR_REPAIR_INPUTS" if status == "HOLD"
                   else "MANUAL_REVIEW_ONLY")
    if audit.get("next_action") != next_action:
        raise ValueError("INCONSISTENT_NEXT_ACTION")
    raw_time = audit.get("checked_at_utc")
    if not isinstance(raw_time, str):
        raise ValueError("MISSING_AUDIT_TIME")
    try:
        stamp = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_AUDIT_TIME") from exc
    if stamp.tzinfo is None:
        raise ValueError("NAIVE_AUDIT_TIME")
    checked = stamp.astimezone(timezone.utc).isoformat(timespec="seconds")
    diagnostics = audit.get("diagnostics")
    if not isinstance(diagnostics, list):
        raise ValueError("INVALID_DIAGNOSTICS")

    lines = [
        "# 足球王者｜ChatGPT Work / Codex 交接摘要",
        "",
        "> 由現有 GitHub Action 唯讀審計生成；不是常駐 GPT，不證明模型準確。",
        "",
        f"- 審計 UTC 時間：{checked}",
        f"- 審計狀態：**{status}**",
        f"- 下一步：**{next_action}**",
        "- 正式投注推薦：**DISABLED**",
        "- 自動投注：**False**",
        "- API 費用：本交接步驟不呼叫外部供應商或 OpenAI API。",
        "",
        "## 待人工確認的診斷",
    ]
    if not diagnostics:
        lines.append("- 沒有列出診斷；不代表已驗證獲利或可投入正式使用。")
    for row in diagnostics[:20]:
        if not isinstance(row, dict):
            lines.append("- UNKNOWN_COMPONENT：UNRECOGNIZED_DIAGNOSTIC")
            continue
        component = row.get("component")
        reason = row.get("reason")
        safe_component = component if isinstance(component, str) and component in _COMPONENTS else "UNKNOWN_COMPONENT"
        safe_reason = reason if isinstance(reason, str) and reason in _REASONS else "UNRECOGNIZED_DIAGNOSTIC"
        lines.append(f"- `{safe_component}`：`{safe_reason}`")
    if len(diagnostics) > 20:
        lines.append(f"- 其餘 {len(diagnostics) - 20} 項請核對原始唯讀審計。")
    lines += [
        "",
        "## 在 ChatGPT Work 交辦下一輪",
        "",
        "請讀取 GitHub 儲存庫 CHANCHUNWA1989/football-king-report 的 AGENTS.md、",
        "最新主分支程式和本次審計。只選一項可重現的風險或故障，",
        "先加測試再提出最小修復，使用獨立分支及草稿 PR，",
        "附實際測試、CI 證據和 GO/HOLD 結論；未驗證不可聲稱成功。",
        "不得讀取／輸出 Secrets、增購 API 配額、修改歷史封存、",
        "解除 DISABLED/HOLD 或進行下注。所有修改需按 PR 流程審核。",
        "",
        "## 重要限制",
        "",
        "- 這份 Markdown 是交接資料；不會自動喚醒 ChatGPT 或呼叫 Codex。",
        "- 資料/賽果證據不足時保持 HOLD，不能用快照新鮮度推論正 EV。",
        "- 如需在 ChatGPT Work 執行，使用者要在產品介面選擇 Work 並授權 GitHub。",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.input.stat().st_size > 2_000_000:
        raise ValueError("OVERSIZED_AUDIT")
    report = json.loads(args.input.read_text(encoding="utf-8"))
    content = render(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
