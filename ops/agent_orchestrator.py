"""Read-only, fail-closed audit of real Football King source snapshots."""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from evidence_merge import validate as validate_settlement

REQUIRED = ("ops/research_recommender.py", "ops/forward_validation.py", "ops/release_guard.py")
SNAPSHOTS = (
    ("market/latest.json", "as_of_utc", 16),
    ("sources/latest.json", "collected_utc", 24),
)

def inspect_snapshot(root, path, timestamp_field, max_age_hours, now):
    item = {"path": path, "status": "HOLD", "reason": "MISSING"}
    try:
        raw = root.joinpath(path).read_bytes()
        if len(raw) > 2_000_000:
            item["reason"] = "OVERSIZED"
            return item
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("INVALID_OBJECT")
        if data.get("production_recommendations") not in (None, "DISABLED"):
            raise ValueError("UNSAFE_PRODUCTION_FLAG")
        value = data.get(timestamp_field)
        if not isinstance(value, str):
            raise ValueError("MISSING_TIMESTAMP")
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("NAIVE_TIMESTAMP")
        age = now - stamp.astimezone(timezone.utc)
        if age < -timedelta(minutes=5):
            raise ValueError("FUTURE_TIMESTAMP")
        if age > timedelta(hours=max_age_hours):
            raise ValueError("STALE")
        if data.get("status") not in ("RESEARCH_ONLY", "READY_RESEARCH"):
            raise ValueError("SOURCE_NOT_READY")
        # A fresh response is not necessarily a usable research dataset.
        if path == "market/latest.json":
            leagues = data.get("leagues")
            if not isinstance(leagues, list) or not leagues:
                raise ValueError("EMPTY_MARKET_COVERAGE")
            if not any(isinstance(row, dict) and type(row.get("events")) is int
                       and row["events"] > 0 and isinstance(row.get("league"), str)
                       and bool(row["league"].strip()) for row in leagues):
                raise ValueError("NO_MARKET_EVENTS")
        elif path == "sources/latest.json":
            providers = data.get("providers")
            if not isinstance(providers, list) or not any(
                isinstance(row, dict) and isinstance(row.get("provider"), str)
                and bool(row["provider"].strip())
                and row.get("configured") is True
                and row.get("status") in ("READY_RESEARCH", "PARTIAL_COVERAGE")
                and type(row.get("sampled_fixture_count")) is int
                and row["sampled_fixture_count"] > 0 for row in providers
            ):
                raise ValueError("EMPTY_SOURCE_COVERAGE")
        item.update(status="READY_RESEARCH", reason=None, timestamp_utc=stamp.astimezone(timezone.utc).isoformat())
    except FileNotFoundError:
        pass
    except (ValueError, TypeError, UnicodeError, OSError, json.JSONDecodeError) as exc:
        item["reason"] = str(exc)[:100]
    return item

def audit(root: Path, now=None):
    now = now or datetime.now(timezone.utc)
    missing = [p for p in REQUIRED if not (root / p).is_file()]
    sources = [inspect_snapshot(root, *s, now) for s in SNAPSHOTS]
    healthy = not missing and all(s["status"] == "READY_RESEARCH" for s in sources)
    provider_coverage = {"usable_provider_count": 0, "sampled_fixture_total": 0}
    if sources[1]["status"] == "READY_RESEARCH":
        try:
            provider_rows = json.loads((root / "sources/latest.json").read_text(encoding="utf-8"))["providers"]
            usable = [p for p in provider_rows if isinstance(p, dict)
                      and p.get("configured") is True
                      and p.get("status") in ("READY_RESEARCH", "PARTIAL_COVERAGE")
                      and type(p.get("sampled_fixture_count")) is int
                      and p["sampled_fixture_count"] > 0]
            provider_coverage["usable_provider_count"] = len(usable)
            provider_coverage["sampled_fixture_total"] = sum(p["sampled_fixture_count"] for p in usable)
        except (ValueError, KeyError, TypeError, OSError):
            pass
    # Fresh metadata alone is not usable global coverage. Fail closed when no provider supplied fixtures.
    if provider_coverage["usable_provider_count"] == 0:
        healthy = False
    diagnostics = ([{"component": p, "reason": "MISSING_COMPONENT"} for p in missing] +
                   [{"component": s["path"], "reason": s["reason"]}
                    for s in sources if s["status"] != "READY_RESEARCH"] +
                   ([{"component": "sources/latest.json", "reason": "NO_USABLE_FIXTURE_PROVIDER"}]
                    if provider_coverage["usable_provider_count"] == 0 else []))
    # A valid source snapshot is not proof of an executed prediction/settlement pipeline.
    evidence_path = root / "evidence/settled.json"
    settlement = {"status": "HOLD", "observations": 0,
                  "independently_verified_observations": 0, "reason": "MISSING"}
    try:
        raw = evidence_path.read_bytes()
        if len(raw) > 8_000_000:
            raise ValueError("OVERSIZED_EVIDENCE")
        data = json.loads(raw)
        if (not isinstance(data, dict) or data.get("schema") != "football-king-forward-research-1"
                or data.get("production_recommendations") != "DISABLED"
                or data.get("results_independently_verified") is not False
                or type(data.get("n")) is not int or not isinstance(data.get("samples"), list)
                or data["n"] != len(data["samples"]) or data["n"] > 20000):
            raise ValueError("INVALID_EVIDENCE")
        stamp = datetime.fromisoformat(data["checked_utc"].replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.astimezone(timezone.utc) > now + timedelta(minutes=5):
            raise ValueError("INVALID_EVIDENCE_TIME")
        validate_settlement(data)
        settlement.update(status="STALE" if now - stamp.astimezone(timezone.utc) > timedelta(hours=48) else "RESEARCH_ONLY", observations=data["n"], reason="SETTLEMENT_OLDER_THAN_48H" if now - stamp.astimezone(timezone.utc) > timedelta(hours=48) else None,
                          checked_utc=stamp.astimezone(timezone.utc).isoformat(),
                          evidence_age_hours=round((now - stamp.astimezone(timezone.utc)).total_seconds() / 3600, 2))
    except FileNotFoundError:
        pass
    except (ValueError, TypeError, KeyError, UnicodeError, OSError) as exc:
        settlement["reason"] = str(exc)[:100]
    if settlement["status"] != "RESEARCH_ONLY":
        diagnostics.append({"component": "evidence/settled.json",
                            "reason": settlement["reason"] or "SETTLEMENT_NOT_READY"})
        healthy = False
    progress = {
        "settlement": settlement,
        "provider_coverage": provider_coverage,
        "target_observations": 1000,
        "remaining_to_target": max(0, 1000 - settlement["observations"]),
        "end_to_end_workflow_verified": False,
        "pre_match_archive_verified": False,
        "post_match_settlement_execution_verified": False,
        "model_superiority_verified": False,
        "all_six_updates_complete": False,
    }
    return {
        "schema": "football-king-agent-audit-v2",
        "checked_at_utc": now.isoformat(),
        "mode": "SHADOW_READ_ONLY",
        "production_recommendations": "DISABLED",
        "automatic_bets": False,
        "status": "READY_FOR_MANUAL_REVIEW" if healthy else "HOLD",
        "missing_components": missing,
        "diagnostics": diagnostics,
        "next_action": "MANUAL_REVIEW_ONLY" if healthy else "REFRESH_OR_REPAIR_INPUTS",
        "sources": sources,
        "six_pillar_progress": progress,
        "actions_performed": [],
        "note": "Snapshot freshness and status are necessary, not proof of full coverage, calibrated predictions, or valid betting prices.",
    }

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
