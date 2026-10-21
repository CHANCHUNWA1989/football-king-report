"""Unify research artifacts without mistaking forecasts for verified results."""
import argparse
import json
from pathlib import Path


def manifest(sealed, model, score, readiness, coverage=None, ft_evidence=None):
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
    if required != 300:
        raise ValueError("UNSUPPORTED_SETTLEMENT_REQUIREMENT")
    marked = readiness.get("result_rows_marked_independently_verified", independent)
    if type(marked) is not int or marked < 0:
        raise ValueError("INVALID_SETTLEMENT_COUNTER")
    # Readiness JSON is not authenticated admission, even when all its flags agree.
    # Preserve reported claims separately; no claim reduces the certified deficit.
    blockers = list(readiness["blockers"])
    if "INSUFFICIENT_INDEPENDENT_SETTLEMENTS" not in blockers:
        blockers.append("INSUFFICIENT_INDEPENDENT_SETTLEMENTS")
    if coverage is not None:
        if not isinstance(coverage, dict) or coverage.get("schema") != "football-king-archive-result-coverage-v1":
            raise ValueError("INVALID_COVERAGE_REPORT")
        if coverage.get("production_recommendations") != "DISABLED" or coverage.get("independently_attested_settlements") != 0:
            raise ValueError("UNSAFE_COVERAGE_REPORT")
        total = coverage.get("sealed_forecasts")
        matching = coverage.get("matching_result_ids")
        missing = coverage.get("missing_result_ids")
        if any(type(v) is not int or v < 0 for v in (total, matching, missing)):
            raise ValueError("INVALID_COVERAGE_COUNTS")
        if total != len(sealed) or matching + missing != total:
            raise ValueError("COVERAGE_COUNT_MISMATCH")
    if ft_evidence is not None:
        if not isinstance(ft_evidence, dict) or ft_evidence.get("schema") != "football-king-two-source-ft-verification-v1":
            raise ValueError("INVALID_FT_EVIDENCE")
        if ft_evidence.get("production_recommendations") != "DISABLED" or ft_evidence.get("external_provenance_rechecked") is not False:
            raise ValueError("UNSAFE_FT_EVIDENCE")
        verified = ft_evidence.get("verified_records")
        count = ft_evidence.get("two_source_verified_count")
        # This pipeline explicitly has no fresh original-evidence verification.
        # Old JSON claims must not be relabelled as certified settlements.
        if type(count) is not int or count != 0 or verified != []:
            raise ValueError("UNAUTHENTICATED_FT_PROMOTION")
        if (ft_evidence.get("independently_verified") is not False
                or ft_evidence.get("eligible_for_model_scoring") is not False):
            raise ValueError("UNAUTHENTICATED_FT_PROMOTION")
        agreements = ft_evidence.get("observation_records")
        observed = ft_evidence.get("observation_consensus_count")
        if not isinstance(agreements, list) or type(observed) is not int or observed != len(agreements):
            raise ValueError("INVALID_FT_OBSERVATION_COUNT")
        if ft_evidence.get("sealed_fixture_count") != len(sealed) or observed > len(sealed):
            raise ValueError("FT_ARCHIVE_MISMATCH")
        ids = [row.get("fixture_id") for row in agreements if isinstance(row, dict)]
        if (len(ids) != observed or any(not isinstance(value, str) for value in ids)
                or len(set(ids)) != observed or not set(ids).issubset({row["fixture_id"] for row in sealed})):
            raise ValueError("INVALID_OBSERVED_FIXTURES")
        if any(row.get("status") != "AGREED_UNVERIFIED" or any(row.get(key) is not False for key in (
                "result_verified", "independently_verified", "eligible_for_model_scoring")) for row in agreements):
            raise ValueError("UNAUTHENTICATED_FT_PROMOTION")
    return {
        "schema": "football-king-unified-research-evidence-v1",
        "status": "HOLD",
        "four_model_sealed_fixture_count": len(sealed),
        "poisson_archived_forecast_count": len(model),
        "sealed_result_id_matches": coverage["matching_result_ids"] if coverage is not None else None,
        "sealed_result_id_missing": coverage["missing_result_ids"] if coverage is not None else None,
        "sealed_result_coverage_is_not_verification": True,
        "two_source_ft_consensus_count": ft_evidence["observation_consensus_count"] if ft_evidence is not None else None,
        "two_source_ft_authenticated_count": 0,
        "two_source_ft_provenance_rechecked_externally": False,
        "independently_verified_settlements_reported": marked,
        "independently_authenticated_settlements": 0,
        "required_independent_settlements": required,
        "remaining_independent_settlements": required,
        "research_score_status": score.get("status"),
        "research_score_accepted": accepted,
        "readiness_blockers": blockers,
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
    certified = data.get("independently_authenticated_settlements", 0)
    if (type(certified) is not int or certified != 0
            or type(data.get("required_independent_settlements")) is not int
            or data["required_independent_settlements"] != 300
            or type(data.get("remaining_independent_settlements")) is not int
            or data["remaining_independent_settlements"] != 300):
        raise ValueError("UNAUTHENTICATED_SETTLEMENT_PROGRESS")
    return "\n".join([
        "足球王者｜每日研究證據摘要",
        "狀態：HOLD｜正式推薦：未開放",
        f"四模型已封存賽前場次：{data['four_model_sealed_fixture_count']}",
        f"Poisson 已封存預測場次：{data['poisson_archived_forecast_count']}",
        "注意：兩條預測來源不可直接相加，亦不等於已核實賽果。",
        "四模型賽果編號配對：" + (str(data["sealed_result_id_matches"]) if data["sealed_result_id_matches"] is not None else "未提供"),
        "四模型缺少賽果編號：" + (str(data["sealed_result_id_missing"]) if data["sealed_result_id_missing"] is not None else "未提供"),
        "編號配對只代表有紀錄，不等於獨立核實。",
        "雙來源賽果一致性配對：" + (str(data["two_source_ft_consensus_count"]) if data["two_source_ft_consensus_count"] is not None else "未提供"),
        "注意：雙來源一致性紀錄尚未重新向外部來源驗證。",
        f"既有報告所列獨立核實賽果：{data['independently_verified_settlements_reported']}",
        f"已認證獨立賽果：{certified}",
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
    p.add_argument("--coverage")
    p.add_argument("--ft-evidence")
    args = p.parse_args()
    def read(path):
        return json.loads(Path(path).read_text(encoding="utf-8"))
    result = manifest(read(args.sealed), read(args.model), read(args.score), read(args.readiness), read(args.coverage) if args.coverage else None, read(args.ft_evidence) if args.ft_evidence else None)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out.with_name("mobile_summary.txt").write_text(mobile_report(result), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
