"""Research-only settlement coverage diagnostics."""

def settlement_gap(count, target=300):
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("INVALID_COUNT")
    return {"verified_count": count, "target": target,
            "remaining": max(target - count, 0),
            "production_recommendations": "DISABLED"}
