"""Research-only final-score corroboration gate.

Independent provider identity must be assigned by trusted ingestion code, not
taken from untrusted fixture payloads. Never infer provider independence from
matching scores alone.
"""

def corroborate(records):
    if not isinstance(records, list) or len(records) > 100:
        raise ValueError("INVALID_RESULT_OBSERVATIONS")
    verified = {}
    for row in records:
        if not isinstance(row, dict):
            raise ValueError("INVALID_RESULT_OBSERVATION")
        event = row.get("event_key")
        provider = row.get("provider")
        score = row.get("score_ft")
        if (not isinstance(event, str) or not event
                or not isinstance(provider, str) or not provider
                or not isinstance(score, list) or len(score) != 2
                or any(type(x) is not int or x < 0 or x > 30 for x in score)
                or row.get("status") != "FINISHED"):
            raise ValueError("INVALID_RESULT_OBSERVATION")
        group = verified.setdefault(event, {})
        value = tuple(score)
        if provider in group and group[provider] != value:
            group[provider] = None
        else:
            group.setdefault(provider, value)
    output = {}
    for event, providers in verified.items():
        values = set(providers.values())
        if None in values or len(values) != 1 or len(providers) < 2:
            output[event] = {"status": "HOLD", "independently_verified": False}
        else:
            output[event] = {"status": "CORROBORATED", "score_ft": list(next(iter(values))),
                             "independently_verified": False,
                             "reason": "PROVIDER_INDEPENDENCE_NOT_ATTESTED"}
    return output
