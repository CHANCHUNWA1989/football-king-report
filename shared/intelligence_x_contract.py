"""Shared research-only aggregate contract. No prices, predictions, orders or claims."""
SCHEMA = "intelligence-x-domain-summary-v1"
DOMAINS = frozenset(("football", "finance"))
MAX_BATCH = 32
FLAGS = {"status": "HOLD", "source_authorized": False,
         "independently_verified": False, "eligible_for_model_scoring": False,
         "production_recommendations": "DISABLED", "live_execution_allowed": False,
         "external_calls": 0}


def make_summary(domain, *, total, candidates, rejected):
    if type(domain) is not str or domain not in DOMAINS:
        raise ValueError("INVALID_DOMAIN")
    if any(type(n) is not int or not 0 <= n <= MAX_BATCH
           for n in (total, candidates, rejected)) or candidates + rejected != total:
        raise ValueError("INVALID_COUNTS")
    return {"schema": SCHEMA, "domain": domain, "total": total,
            "candidates": candidates, "rejected": rejected, **FLAGS}


def validate_summary(record, *, expected_domain):
    if type(record) is not dict:
        raise ValueError("INVALID_SUMMARY")
    expected = make_summary(expected_domain, total=record.get("total"),
                            candidates=record.get("candidates"), rejected=record.get("rejected"))
    if record.keys() != expected.keys():
        raise ValueError("UNEXPECTED_FIELDS")
    if any(type(record[k]) is not type(v) or record[k] != v
           for k, v in expected.items()):
        raise ValueError("DOMAIN_OR_SAFETY_MISMATCH")
    return expected
