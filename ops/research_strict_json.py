"""Pure JSON validation helpers for offline research; no transport or credentials."""
def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("DUPLICATE_JSON_KEY")
        obj[key] = value
    return obj

def reject_constant(value):
    raise ValueError("NONFINITE_JSON")
