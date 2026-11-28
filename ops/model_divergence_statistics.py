"""Descriptive within-archive model disagreement; never independent validation."""
from collections import Counter
from itertools import combinations
import gzip
import io
import json
from ops.model_divergence_archive import inspect_archive, MAX_DECOMPRESSED
from ops.model_divergence_evidence import _unique, _reject, _finite
from ops.model_divergence_guard import _id, _utc, _vector

MODELS = ("A", "B", "C", "D")
THRESHOLD = 0.10
BASE = "poisson-shrinkage-unvalidated-v4.1"
SHRINK = "probability-shrink-to-uniform-fixed-0.15-v1"
OPPONENT = "opponent-adjusted-decay90-shrink8-v1"
DIXON = "dixon-coles-fixed-rate-rho-minus005-forward-research-v1"


def _index(rows):
    if type(rows) is not list or len(rows) > 49:
        raise ValueError("INVALID_ROWS")
    out = {}
    for row in rows:
        if type(row) is not dict:
            raise ValueError("INVALID_ROW")
        key = _id(row["event_id"])
        if key in out:
            raise ValueError("DUPLICATE_EVENT")
        out[key] = row
    return out


def _leaders(p):
    return frozenset(i for i, value in enumerate(p) if max(p)-value <= 1e-12)


def _gap(p, q):
    return max(abs(x-y) for x,y in zip(p,q))


def _diagnose(doc):
    """Validate declared model identities, clocks and original-vector linkage."""
    base = _index(doc["predictions"])
    cdoc = doc["opponent_adjusted_forward_challenger"]
    ddoc = doc["fixed_low_score_challenger"]
    if (doc["ab_model"] != SHRINK or cdoc["model"] != OPPONENT
            or ddoc["model_id"] != DIXON
            or any(x["production_recommendations"] != "DISABLED" for x in (cdoc,ddoc))):
        raise ValueError("MODEL_IDENTITY")
    c, d = _index(cdoc["predictions"]), _index(ddoc["predictions"])
    if not set(c) <= set(base) or not set(d) <= set(base):
        raise ValueError("OUT_OF_SCOPE")
    if any(type(x["predictions_count"]) is not int or x["predictions_count"] != len(y)
           for x,y in ((cdoc,c),(ddoc,d))):
        raise ValueError("COUNT_MISMATCH")
    categories = Counter()
    pairs = {i+j: dict(n=0, direction_conflicts=0, max_gap=0.0)
             for i,j in combinations(MODELS,2)}
    max_gap = 0.0
    for event, a in base.items():
        if event not in c or event not in d:
            categories["incomplete"] += 1
            continue
        b, e = c[event], d[event]
        if (a["model"] != BASE or a["ab_model"] != SHRINK
                or a["ab_unvalidated"] is not True or a["calibrated"] is not False
                or e["model_id"] != DIXON or e["source_model"] != BASE
                or any(x["production_recommendations"] != "DISABLED" for x in (a,b,e))):
            raise ValueError("ROW_MODEL_IDENTITY")
        for key in ("league","home","away"):
            if not _id(a[key]) == _id(b[key]) == _id(e[key]):
                raise ValueError("FIXTURE_MISMATCH")
        ko = _utc(a["kickoff_utc"])
        t = _utc(a["prediction_utc"])
        if (not ko == _utc(b["kickoff_utc"]) == _utc(e["kickoff_utc_recorded"])
                or not t == _utc(b["original_prediction_utc"]) == _utc(e["source_prediction_utc"])
                or not t <= _utc(b["candidate_prediction_utc"]) < ko
                or not t <= _utc(e["candidate_generated_utc"]) == _utc(e["prediction_utc"]) < ko):
            raise ValueError("CLOCK_MISMATCH")
        pa = _vector([a["p_home"],a["p_draw"],a["p_away"]])
        if any(_gap(pa,_vector(x["original"])) > 1e-5 for x in (b,e)):
            raise ValueError("ORIGINAL_VECTOR_MISMATCH")
        vectors = (pa, _vector([a["ab_candidate_p_home"],a["ab_candidate_p_draw"],
                                a["ab_candidate_p_away"]]), _vector(b["p"]), _vector(e["candidate"]))
        leaders = tuple(_leaders(v) for v in vectors)
        largest = 0.0
        for i,j in combinations(range(4),2):
            p = pairs[MODELS[i]+MODELS[j]]
            gap = _gap(vectors[i],vectors[j])
            largest = max(largest,gap)
            p["n"] += 1
            p["direction_conflicts"] += int(leaders[i] != leaders[j])
            p["max_gap"] = max(p["max_gap"],gap)
        max_gap = max(max_gap,largest)
        category = ("direction_conflict" if len(set(leaders)) > 1 else
                    "large_gap" if largest >= THRESHOLD-1e-12 else
                    "no_large_disagreement")
        categories[category] += 1
    return dict(categories=dict(categories), pairwise=pairs,
                complete_count=len(base)-categories["incomplete"],
                max_gap=max_gap)


def summarize_archive(data):
    out = dict(status="HOLD", production_recommendations="DISABLED",
               can_recommend_bets=False, source_authenticated=False,
               independent_model_evidence=False, model_calibrated=False,
               certified_outcomes=0, qualified_external_pairs=0,
               threshold_calibrated=False, diagnostic_threshold=THRESHOLD,
               archive_diagnostics_valid=False, categories={}, pairwise={},
               complete_count=0, max_gap=None)
    if not inspect_archive(data)["archive_blob_match"]:
        return out
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data),mode="rb") as stream:
            payload=stream.read(MAX_DECOMPRESSED+1)
        if len(payload)>MAX_DECOMPRESSED:
            return out
        doc=json.loads(payload.decode("utf-8"),object_pairs_hook=_unique,
                       parse_constant=_reject,parse_float=_finite)
        details=_diagnose(doc)
    except (ValueError, TypeError, KeyError, OverflowError, OSError, EOFError, RecursionError):
        return out
    return {**out, **details, "archive_diagnostics_valid":True}
