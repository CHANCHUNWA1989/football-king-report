"""Explicit cross-provider binding for the offline divergence batch.

Manifest and source metadata are caller claims, not authenticated source
proof. No network access, name matching, inferred clocks, or model promotion.
"""
import re
from ops.model_divergence_guard import _id, _utc
from ops.model_divergence_batch import evaluate, MAX_FIXTURES

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_NATIVE = ("native_event_id", "native_home_id", "native_away_id")
_KEYS = ("event_id", "league", "home_id", "away_id")


def _native(row):
    values = tuple(_id(row[k]) for k in _NATIVE)
    if values[1] == values[2]:
        raise ValueError("NATIVE_SELF_MATCH")
    return values


def compare(manifest, left_rows, right_rows, *, left_provider, right_provider,
            left_model, right_model, as_of_utc):
    blocked = dict(status="HOLD", reason="INVALID_BINDING", results=[], counts={},
                   source_authenticated=False, native_identity_authenticated=False,
                   source_bytes_verified=False, model_calibrated=False,
                   production_recommendations="DISABLED", can_recommend_bets=False)
    try:
        now = _utc(as_of_utc)
        providers = tuple(_id(x) for x in (left_provider, right_provider))
        models = tuple(_id(x) for x in (left_model, right_model))
        if len(set(providers)) != 2 or len(set(models)) != 2:
            raise ValueError("DUPLICATE_SOURCE_OR_MODEL")
        if type(manifest) is not list or not 1 <= len(manifest) <= MAX_FIXTURES:
            raise ValueError("INVALID_MANIFEST")
        bindings = {}
        native_seen = [set(), set()]
        fixtures = set()
        for m in manifest:
            canonical = tuple(_id(m[k]) for k in _KEYS)
            event, league, home, away = canonical
            ko = _utc(m["kickoff_utc"])
            if event in bindings or home == away:
                raise ValueError("DUPLICATE_OR_SELF_MATCH")
            fixture = (league, ko, tuple(sorted((home, away))))
            if fixture in fixtures:
                raise ValueError("DUPLICATE_CANONICAL_FIXTURE")
            fixtures.add(fixture)
            sides = tuple(_native(m[k]) for k in ("left", "right"))
            for i, side in enumerate(sides):
                if side[0] in native_seen[i]:
                    raise ValueError("DUPLICATE_NATIVE_EVENT")
                native_seen[i].add(side[0])
            bindings[event] = (canonical, ko, sides)
        clean = []
        for i, rows in enumerate((left_rows, right_rows)):
            if type(rows) is not list or len(rows) > MAX_FIXTURES:
                raise ValueError("INVALID_ROWS")
            side_rows = []
            for row in rows:
                if type(row) is not dict:
                    raise ValueError("INVALID_ROW")
                ids = tuple(_id(row[k]) for k in _KEYS)
                expected, ko, sides = bindings[ids[0]]
                if (ids != expected or _utc(row["kickoff_utc"]) != ko
                        or _native(row) != sides[i]
                        or row["provider_id"] != providers[i]
                        or row["model_id"] != models[i]):
                    raise ValueError("BINDING_MISMATCH")
                digest = row["source_sha256"]
                if type(digest) is not str or not _HEX.fullmatch(digest):
                    raise ValueError("MISSING_DIGEST_CLAIM")
                updated, captured, cutoff, predicted = (
                    _utc(row[k]) for k in ("source_updated_utc", "source_captured_utc",
                                          "information_cutoff_utc", "prediction_utc"))
                if not updated <= captured <= cutoff <= predicted <= now < ko:
                    raise ValueError("INVALID_SOURCE_CHRONOLOGY")
                if (now - updated).total_seconds() > 36000:
                    raise ValueError("STALE_SOURCE")
                side_rows.append({k: row[k] for k in (*_KEYS, "kickoff_utc",
                                  "model_id", "information_cutoff_utc",
                                  "prediction_utc", "p")})
            clean.append(side_rows)
    except (ValueError, KeyError, TypeError, OverflowError, AttributeError):
        return blocked
    result = evaluate(list(bindings), *clean, as_of_utc=as_of_utc)
    return {**result, "native_identity_authenticated": False,
            "source_bytes_verified": False}
