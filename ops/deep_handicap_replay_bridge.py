"""Private capture-to-evaluation bridge; structural replay, not authentication."""
import copy
import hmac
import math
import re
from datetime import timedelta
from asian_handicap_research import TYPES, grade, quarter_units
from deep_handicap_private_capture import SCHEMA as CAPTURE_SCHEMA, _digest
from live_score_identity_guard import check, parse_utc

SCHEMA="football-king-dhe-replay-bridge-v1"
HASH=re.compile(r"[0-9a-f]{64}")
IDENTITY=("league_id","fixture_id","home_id","away_id","kickoff_utc",
          "side","handicap","information_cutoff_utc")
MODELS={"baseline":"dhe-independent-poisson-rounded-v1",
        "challenger":"dhe-halftime-two-goal-pace085-v1"}


def _require(value, reason):
    if not value:
        raise ValueError(reason)


def _hash(v):
    return type(v) is str and HASH.fullmatch(v) is not None


def bridge(capture_report, mapping, observations, *, expected_candidate_sha256,
           as_of_utc, data_kind):
    """Bind declared pre-match digest and source identities to result claims.

    expected_candidate_sha256 and mapping are caller claims, not external
    witnesses. Output is only SYNTHETIC or EXTERNAL_UNAUTHENTICATED.
    Never fetch sources, modify capture bytes or authenticate a result.
    """
    out={"schema":SCHEMA,"status":"HOLD","production_recommendations":"DISABLED",
         "research_only":True,"private_output_only":True,
         "source_authenticated":False,"external_witness_verified":False,
         "true_forward_sample_count":0,"qualifies_for_betting":False,
         "positive_expected_value_verified":False,"evaluation_row":None}
    try:
        _require(data_kind in ("SYNTHETIC","EXTERNAL_UNAUTHENTICATED"),"BAD_DATA_KIND")
        _require(type(capture_report) is dict and
                 capture_report.get("schema")==CAPTURE_SCHEMA and
                 capture_report.get("status")=="HOLD" and
                 capture_report.get("production_recommendations")=="DISABLED" and
                 capture_report.get("source_authenticated") is False and
                 capture_report.get("external_archive_witness_verified") is False and
                 capture_report.get("true_forward_sample_count")==0,"BAD_CAPTURE_REPORT")
        c=capture_report["candidate"]
        _require(type(c) is dict and c.get("data_kind")=="EXTERNAL_UNAUTHENTICATED"
                 and c.get("production_recommendations")=="DISABLED"
                 and not any(k in c for k in ("results","score_ft","result","y")),
                 "BAD_CANDIDATE")
        digest=_digest(c)
        _require(_hash(expected_candidate_sha256) and
                 hmac.compare_digest(digest,expected_candidate_sha256) and
                 capture_report.get("candidate_sha256")==digest,"CANDIDATE_DIGEST_MISMATCH")
        identity={k:c[k] for k in IDENTITY}
        ko,cutoff,now=map(parse_utc,(c["kickoff_utc"],c["information_cutoff_utc"],as_of_utc))
        units=quarter_units(c["handicap"])
        _require(c["side"] in ("HOME","AWAY") and units<=-6 and
                 cutoff<ko-timedelta(minutes=10) and now>=ko+timedelta(minutes=105),
                 "BAD_CANDIDATE_CHRONOLOGY_OR_LINE")
        _require(type(c["evidence"]) is dict and
                 parse_utc(c["evidence"]["recorded_capture_utc"])==cutoff,
                 "BAD_CAPTURE_CHRONOLOGY")
        feasible={grade(max(0,m),max(0,-m),"HOME",units/4) for m in range(-25,26)}
        for name,model in MODELS.items():
            p=c[name]
            _require(all(p[k]==v for k,v in identity.items()) and
                     p["model_id"]==model and _hash(p["archive_reference"]) and
                     parse_utc(p["recorded_utc"])==cutoff,"PREDICTION_CONTRACT_MISMATCH")
            probs=p["probabilities"]
            _require(type(probs) is dict and set(probs)==set(TYPES) and
                     all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=1
                         for v in probs.values()) and abs(math.fsum(probs.values())-1)<=1e-8
                     and all(probs[g]<=1e-8 for g in TYPES if g not in feasible),
                     "BAD_PREDICTION_DISTRIBUTION")
        _require(type(mapping) is dict and mapping["candidate_sha256"]==digest
                 and mapping["fixture_id"]==c["fixture_id"] and
                 mapping["league"]==c["league_id"] and mapping["home_id"]==c["home_id"]
                 and mapping["away_id"]==c["away_id"] and
                 parse_utc(mapping["kickoff_utc"])==ko,"MAPPING_IDENTITY_MISMATCH")
        sealed=parse_utc(mapping["expected_identity_sealed_utc"])
        _require(cutoff<=sealed<ko-timedelta(minutes=10),"MAPPING_NOT_PREMATCH")
        checked=check(mapping,observations,as_of_utc)
        _require(checked["status"]=="RESEARCH_ONLY" and checked["match_status"]=="FINISHED",
                 "RESULT_IDENTITY_GATE_REJECTED")
        results=[]
        hashes=set()
        for obs in observations:
            _require(obs.get("result_scope")=="REGULATION_90_MINUTES" and
                     parse_utc(obs["kickoff_utc"])==ko and
                     parse_utc(obs["source_updated_utc"])>=ko+timedelta(minutes=105),
                     "REGULATION_RESULT_OR_CLOCK_REJECTED")
            evidence=obs.get("evidence_sha256")
            _require(_hash(evidence) and evidence not in hashes,"MISSING_OR_DUPLICATE_RESULT_DIGEST")
            hashes.add(evidence)
            score=[obs["score_home"],obs["score_away"]]
            _require(all(type(v) is int and 0<=v<=25 for v in score),"BAD_REGULATION_SCORE")
            results.append({**{k:identity[k] for k in IDENTITY[:5]},
                            "provider_id":obs["provider"],"evidence_reference":evidence,
                            "status":"FINISHED_90_MINUTES","captured_utc":obs["captured_utc"],
                            "score_ft":score})
        row={**copy.deepcopy(identity),"data_kind":data_kind,
             "baseline":copy.deepcopy(c["baseline"]),"challenger":copy.deepcopy(c["challenger"]),
             "results":results,"candidate_sha256":digest}
        out.update(reason="STRUCTURAL_REPLAY_READY_UNAUTHENTICATED",evaluation_row=row)
    except (ValueError,TypeError,KeyError,OverflowError,AttributeError,RecursionError) as exc:
        allowed={"BAD_DATA_KIND","BAD_CAPTURE_REPORT","BAD_CANDIDATE","CANDIDATE_DIGEST_MISMATCH",
                 "BAD_CANDIDATE_CHRONOLOGY_OR_LINE","BAD_CAPTURE_CHRONOLOGY",
                 "PREDICTION_CONTRACT_MISMATCH","BAD_PREDICTION_DISTRIBUTION",
                 "MAPPING_IDENTITY_MISMATCH","MAPPING_NOT_PREMATCH","RESULT_IDENTITY_GATE_REJECTED",
                 "REGULATION_RESULT_OR_CLOCK_REJECTED","MISSING_OR_DUPLICATE_RESULT_DIGEST",
                 "BAD_REGULATION_SCORE"}
        out["reason"]=str(exc) if str(exc) in allowed else "INVALID_BRIDGE_INPUT"
    return out
