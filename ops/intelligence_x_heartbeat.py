"""Offline P25 heartbeat exporter. No networking, scheduling or authorization."""
import json
import sys
from datetime import datetime, timezone

from intelligence_x_live_evidence import audit_live, _utc

MAX_BYTES = 65536


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("DUPLICATE_JSON_KEY")
        out[key] = value
    return out


def _constant(_):
    raise ValueError("NONFINITE_JSON")


def heartbeat(raw, *, now_utc):
    _utc(now_utc)
    result = {
        "schema": "intelligence-x-heartbeat-v1",
        "generated_at": now_utc, "oldest_update_at": None,
        "diagnostic": "BLOCKED", "source_count": 0,
        "status": "HOLD", "production_recommendations": "DISABLED",
        "source_authorized": False, "independently_verified": False,
        "eligible_for_model_scoring": False, "external_calls": 0,
    }
    try:
        if type(raw) is not bytes or len(raw) > MAX_BYTES:
            raise ValueError("INVALID_INPUT_SIZE")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=_constant)
        if type(data) is not dict or data.keys() != {"fixture_id", "registry", "snapshots"}:
            raise ValueError("INVALID_INPUT_FIELDS")
        audit = audit_live(data["snapshots"], fixture_id=data["fixture_id"],
                           registry=data["registry"], now_utc=now_utc)
        result["source_count"] = audit["source_count"]
        if audit["diagnostic"] == "AGREEMENT_CANDIDATE":
            result["diagnostic"] = audit["diagnostic"]
            result["oldest_update_at"] = min(r["updated_at"] for r in data["snapshots"])
    except (ValueError, TypeError, OverflowError, RecursionError):
        pass
    return result


def main():
    raw = sys.stdin.buffer.read(MAX_BYTES + 1)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(json.dumps(heartbeat(raw, now_utc=now), sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
