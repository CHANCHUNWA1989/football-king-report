"""Read-only, fail-closed orchestration audit of existing Football King outputs."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

REQUIRED = ("ops/research_recommender.py", "ops/forward_validation.py", "ops/release_guard.py")
def audit(root: Path, now=None):
    now = now or datetime.now(timezone.utc)
    missing = [p for p in REQUIRED if not (root / p).is_file()]
    report = {
        "schema": "football-king-agent-audit-v1",
        "checked_at_utc": now.isoformat(),
        "mode": "SHADOW_READ_ONLY",
        "production_recommendations": "DISABLED",
        "automatic_bets": False,
        "status": "HOLD" if missing else "READY_FOR_MANUAL_REVIEW",
        "missing_components": missing,
        "actions_performed": [],
        "note": "Component presence is not proof of working data, calibration, CI success, or prediction quality."
    }
    return report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.root)
    data = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(data + "\n", encoding="utf-8")
    print(data)
    return 0 if result["status"] != "HOLD" else 2

if __name__ == "__main__":
    raise SystemExit(main())
