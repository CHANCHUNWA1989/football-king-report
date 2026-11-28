"""Optional read-only evidence from the exact normalized gateway response.

Capture before schedule enrichment. Requested competition context is not
publisher-authenticated competition identity. Never infer missing native IDs
or rewrite a legacy archive. No source calls or forecast inputs are added.
"""
import hashlib
import json
from datetime import datetime, timezone
from collections import Counter

LEAGUES = {"epl", "championship", "bundesliga", "laliga", "seriea", "ligue1"}
MAX_ROWS = 1200


def utc(value):
    if not isinstance(value, str):
        raise ValueError("MISSING_TIMESTAMP")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return stamp.astimezone(timezone.utc)


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode("utf-8")).hexdigest()


def capture_batch(league, season, raw, observed, *, replay):
    """Retain a bounded projection, including explicit missing values."""
    result = {"requested_league": league, "season": season, "replay": replay,
              "observed_utc": observed.isoformat(), "status": "HOLD",
              "source": raw.get("source"), "source_url": raw.get("source_url"),
              "reported_capture_utc": raw.get("captured_utc"),
              "rows": [], "rejected": {}, "identity_authenticated": False}
    rows = raw.get("matches")
    if (league not in LEAGUES or raw.get("status") != "READY_RESEARCH"
            or raw.get("league") not in (None, league)
            or not isinstance(rows, list) or len(rows) > MAX_ROWS):
        result["reason"] = "INVALID_OR_OVERSIZE_BATCH"
        return result
    result["input_row_count"] = len(rows)
    result["gateway_reported_league"] = raw.get("league")
    counts = Counter()
    try:
        source_at = utc(raw.get("captured_utc"))
        if source_at > observed:
            raise ValueError("FUTURE_CAPTURE")
        if not (isinstance(raw.get("source"), str) and raw["source"].strip()
                and isinstance(raw.get("source_url"), str)
                and raw["source_url"].startswith("https://")):
            raise ValueError("MISSING_SOURCE")
        result["source_context_complete"] = True
    except (ValueError, TypeError, OverflowError):
        result["source_context_complete"] = False
    for row in rows:
        if not isinstance(row, dict):
            counts["INVALID_ROW"] += 1
            continue
        if row.get("league") not in (None, league):
            counts["ROW_COMPETITION_CONFLICT"] += 1
            continue
        projection = {k: row.get(k) for k in
                      ("league", "event_id", "date", "home", "away",
                       "kickoff_utc", "status")}
        # Native input is retained only if the existing gateway supplied it.
        # No score or derived fixture is added to this optional evidence.
        result["rows"].append(projection)
    result["rejected"] = dict(counts)
    result["projection_sha256"] = digest(result["rows"])
    result["status"] = "RESEARCH_ONLY" if result["source_context_complete"] else "HOLD"
    return result


def assemble(batches, completed, *, clock_problem=None):
    return {"schema": "football-king-gateway-source-evidence-v1",
            "completed_utc": completed.isoformat(), "batches": batches,
            "batch_count": len(batches), "clock_problem": clock_problem,
            "batches_sha256": digest(batches), "status": "HOLD",
            "competition_identity_authenticated": False,
            "source_identity_authenticated": False,
            "missing_gateway_fixtures_proven": False,
            "admitted_new_fixtures": 0,
            "production_recommendations": "DISABLED"}


def verify_for_artifact(doc):
    """Check exact projection digests and public metadata before upload.

    An incomplete batch is diagnostic, not grounds to infer identity.
    No raw responses, odds, scores, credentials, or arbitrary URL hosts.
    """
    from urllib.parse import urlsplit
    top_fields={"schema","completed_utc","batches","batch_count","clock_problem",
                "batches_sha256","status","competition_identity_authenticated",
                "source_identity_authenticated","missing_gateway_fixtures_proven",
                "admitted_new_fixtures","production_recommendations"}
    if (not isinstance(doc,dict) or set(doc)!=top_fields
            or doc.get("clock_problem") not in (None,"GENERATION_CLOCK_UNAVAILABLE",
                "GENERATION_CLOCK_REWOUND","GENERATION_HK_CALENDAR_DAY_CHANGED")
            or type(doc.get("admitted_new_fixtures")) is not int
            or type(doc.get("batch_count")) is not int
            or doc.get("schema") != "football-king-gateway-source-evidence-v1"
            or doc.get("status") != "HOLD"
            or doc.get("production_recommendations") != "DISABLED"
            or doc.get("admitted_new_fixtures") != 0
            or any(doc.get(k) is not False for k in
                   ("competition_identity_authenticated", "source_identity_authenticated",
                    "missing_gateway_fixtures_proven"))):
        raise ValueError("SOURCE_EVIDENCE_GUARD")
    batches = doc["batches"]
    if (not isinstance(batches, list) or len(batches)>len(LEAGUES)
            or doc["batch_count"] != len(batches) or doc["batches_sha256"] != digest(batches)):
        raise ValueError("SOURCE_BATCH_DIGEST")
    completed = utc(doc["completed_utc"])
    seen = set()
    rows = complete = explicit_ids = explicit_league = 0
    fields = {"league", "event_id", "date", "home", "away", "kickoff_utc", "status"}
    base_fields={"requested_league","season","replay","observed_utc","status",
                 "source","source_url","reported_capture_utc","rows","rejected",
                 "identity_authenticated"}
    valid_fields=base_fields|{"input_row_count","gateway_reported_league",
                              "source_context_complete","projection_sha256"}
    for b in batches:
        if not isinstance(b,dict) or set(b) not in (valid_fields,base_fields|{"reason"}):
            raise ValueError("SOURCE_BATCH_FIELDS")
        league = b["requested_league"]
        if league not in LEAGUES or league in seen or b.get("identity_authenticated") is not False:
            raise ValueError("SOURCE_BATCH_IDENTITY")
        seen.add(league)
        if b.get("replay") is not False:
            raise ValueError("REPLAY_NOT_LIVE")
        observed=utc(b["observed_utc"])
        if observed > completed:
            raise ValueError("SOURCE_BATCH_CLOCK")
        url = b.get("source_url")
        if url is not None:
            if not isinstance(url, str) or len(url)>2048:
                raise ValueError("SOURCE_URL")
            u = urlsplit(url)
            if (u.scheme!="https" or u.netloc not in {"raw.githubusercontent.com", "api.openligadb.de"}
                    or u.query or u.fragment
                    or (u.netloc=="raw.githubusercontent.com" and not u.path.startswith("/openfootball/football.json/"))
                    or (u.netloc=="api.openligadb.de" and not u.path.startswith("/getmatchdata/"))):
                raise ValueError("SOURCE_URL_NOT_PUBLIC_ALLOWLIST")
        for key in ("source", "reported_capture_utc", "season", "gateway_reported_league"):
            v = b.get(key)
            if v is not None and (not isinstance(v,str) or len(v)>256):
                raise ValueError("SOURCE_CONTEXT_FIELD")
        projection = b["rows"]
        if (not isinstance(projection,list) or len(projection)>MAX_ROWS
                or (projection or "projection_sha256" in b) and b.get("projection_sha256")!=digest(projection)):
            raise ValueError("SOURCE_PROJECTION_DIGEST")
        if "reason" in b:
            if (b["reason"]!="INVALID_OR_OVERSIZE_BATCH" or projection
                    or b["rejected"]!={} or b["status"]!="HOLD"):
                raise ValueError("SOURCE_INVALID_BATCH_STATE")
        else:
            rejected=b["rejected"]
            n=b["input_row_count"]
            if (not isinstance(rejected,dict)
                    or set(rejected)-{"INVALID_ROW","ROW_COMPETITION_CONFLICT"}
                    or any(type(v) is not int or v<=0 for v in rejected.values())
                    or type(n) is not int or not 0<=n<=MAX_ROWS
                    or n!=len(projection)+sum(rejected.values())
                    or b["gateway_reported_league"] not in (None,league)):
                raise ValueError("SOURCE_BATCH_ACCOUNTING")
            try:
                context=bool(isinstance(b["source"],str) and b["source"].strip()
                             and url and utc(b["reported_capture_utc"])<=observed)
            except (ValueError,TypeError,OverflowError):
                context=False
            if (b["source_context_complete"] is not context
                    or b["status"]!=("RESEARCH_ONLY" if context else "HOLD")):
                raise ValueError("SOURCE_CONTEXT_CONTRADICTION")
        for r in projection:
            if not isinstance(r,dict) or set(r)!=fields or any(v is not None and (not isinstance(v,str) or len(v)>512) for v in r.values()):
                raise ValueError("SOURCE_PROJECTION_FIELD")
            if r["league"] not in (None,league):
                raise ValueError("SOURCE_PROJECTION_LEAGUE")
            explicit_ids += int(bool(r["event_id"]))
            explicit_league += int(r["league"]==league)
        rows += len(projection)
        complete += int(b.get("source_context_complete") is True)
    return {"batch_count":len(batches), "source_context_complete_batches":complete,
            "normalized_projection_rows":rows, "rows_with_explicit_event_id":explicit_ids,
            "rows_with_explicit_league":explicit_league,
            "clock_problem":doc.get("clock_problem"), "admitted_new_fixtures":0,
            "production_recommendations":"DISABLED", "status":"HOLD"}
