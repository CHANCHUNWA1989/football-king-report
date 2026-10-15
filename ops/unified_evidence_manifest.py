"""Unify research artifacts without mistaking forecasts for verified results."""
import argparse
import json
from pathlib import Path


def manifest(sealed, model, score, readiness):
    if not isinstance(sealed, list) or not isinstance(model, list):
        raise ValueError("INVALID_FORECAST_COLLECTION")
    if not isinstance(score, dict) or not isinstance(readiness, dict):
        raise ValueError("INVALID_REPORT")
    if score.get("production_recommendations") != "DISABLED" or readiness.get("production_recommendations") != "DISABLED":
        raise ValueError("UNSAFE_RESEARCH_INPUT")
    if readiness.get("ready_for_production") is not False:
        raise ValueError("UNVERIFIED_PRODUCTION_CLAIM")
    seen = set()
    for row in sealed:
        if not isinstance(row, dict) or row.get("production_recommendations") != "DISABLED":
            raise ValueError("UNSAFE_SEALED_ROW")
        identifier = row.get("fixture_id")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ValueError("DUPLICATE_OR_INVALID_SEAL")
        seen.add(identifier)
    seen = set()
    for row in model:
        if not isinstance(row, dict) or row.get("production_recommendations") != "DISABLED":
            raise ValueError("UNSAFE_MODEL_ROW")
        identifier = row.get("event_id")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ValueError("DUPLICATE_OR_INVALID_MODEL")
        if row.get("independently_verified") is not False:
            raise ValueError("MODEL_FORECAST_MISLABELED_AS_RESULT")
        seen.add(identifier)
    if score.get("status") not in ("HOLD", "RESEARCH_ONLY"):
        raise ValueError("INVALID_SCORE_STATUS")
    accepted = score.get("accepted")
    if type(accepted) is not int or accepted < 0:
        raise ValueError("INVALID_ACCEPTED_COUNT")
    if accepted > 0 and not model:
        raise ValueError("ACCEPTED_WITHOUT_MODEL_FORECASTS")
    if not isinstance(readiness.get("blockers"), list) or not all(isinstance(x, str) for x in readiness["blockers"]):
        raise ValueError("INVALID_BLOCKERS")
    independent = readiness.get("independently_verified_settlements")
    required = readiness.get("required_independent_settlements")
    if type(independent) is not int or type(required) is not int or independent < 0 or required < 1:
        raise ValueError("INVALID_SETTLEMENT_COUNTER")
    return {
        "schema": "football-king-unified-research-evidence-v1",
        "status": "HOLD",
        "four_model_sealed_fixture_count": len(sealed),
        "poisson_archived_forecast_count": len(model),
        "independently_verified_settlements_reported": independent,
        "required_independent_settlements": required,
        "remaining_independent_settlements": max(0, required - independent),
        "research_score_status": score.get("status"),
        "research_score_accepted": accepted,
        "readiness_blockers": readiness["blockers"],
        "counts_are_from_distinct_pipelines_not_additive": True,
        "forecasts_are_not_settlements": True,
        "independent_verification_not_attested_by_this_manifest": True,
        "ready_for_production": False,
        "production_recommendations": "DISABLED",
    }


def mobile_report(data):
    """Plain-text phone report; counts remain explicitly non-additive."""
    if data.get("schema") != "football-king-unified-research-evidence-v1" or data.get("production_recommendations") != "DISABLED":
        raise ValueError("UNSAFE_MANIFEST")
    return "\n".join([
        "足球王者｜每日研究證據摘要",
        "狀態：HOLD｜正式推薦：未開放",
        f"四模型已封存賽前場次：{data['four_model_sealed_fixture_count']}",
        f"Poisson 已封存預測場次：{data['poisson_archived_forecast_count']}",
        "注意：兩條預測來源不可直接相加，亦不等於已核實賽果。",
        f"既有報告所列獨立核實賽果：{data['independently_verified_settlements_reported']}",
        f"獨立核實目標：{data['required_independent_settlements']}",
        f"仍差：{data['remaining_independent_settlements']}",
        f"研究評分狀態：{data['research_score_status']}",
        f"研究評分已接納配對：{data['research_score_accepted']}",
        "尚未通過條件：" + ("、".join(data["readiness_blockers"]) if data["readiness_blockers"] else "仍須完成樣本外驗收"),
        "此摘要只轉述既有驗證進度，並非額外獨立驗證。",
        "投注及正式推薦：DISABLED",
        "",
    ])


def main():
    p = argparse.ArgumentParser()
    for flag in ("sealed", "model", "score", "readiness", "output"):
        p.add_argument("--" + flag, required=True)
    args = p.parse_args()
    def read(path):
        return json.loads(Path(path).read_text(encoding="utf-8"))
    result = manifest(read(args.sealed), read(args.model), read(args.score), read(args.readiness))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out.with_name("mobile_summary.txt").write_text(mobile_report(result), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
