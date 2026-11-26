"""V20 offline signed receipt verification, not release authority.

Trust policy must be provisioned outside the prediction producer and its SHA256
pinned independently. Signed statements do not themselves prove upstream facts,
organizational independence, or trusted clock operation. No keys or providers
are enrolled by this module. No prospective credit is granted.
"""
import hashlib
import json
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path
from ops.v6_forward_bundle import decode,digest,utc,native
from ops.v6_forward_archive_audit import audit
from ops.v5_ensemble_competition import metrics,vec

DOMAIN=b"football-king/v20-signed-receipt/v1\x00"
DER_PREFIX=bytes.fromhex("302a300506032b6570032100")
MAX_RECEIPT=16384
MAX_RAW=3_000_000
ROLES=("witness","result")

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def exact(d,keys):
    if type(d) is not dict or set(d)!=set(keys):raise ValueError("RECEIPT_FIELDS")
    return d

def bounded(raw,n):
    if type(raw) is not bytes or not 0<len(raw)<=n:raise ValueError("RECEIPT_SIZE")
    return raw

def hexbytes(value,n):
    if type(value) is not str or len(value)!=2*n or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("KEY_OR_SIGNATURE_FORMAT")
    return bytes.fromhex(value)

def name(x):
    if type(x) is not str or not 1<=len(x)<=128 or not x.isascii() or x!=x.strip() or not all(c.isalnum() or c in "._-" for c in x):
        raise ValueError("TRUST_IDENTITY")
    return x

def trust_policy(raw,expected):
    bounded(raw,MAX_RECEIPT)
    if sha(raw)!=digest(expected):raise ValueError("TRUST_POLICY_DIGEST")
    doc=exact(decode(raw),("schema","keys"))
    if doc["schema"]!="v20-independent-trust-policy-v1" or type(doc["keys"]) is not list or not 3<=len(doc["keys"])<=20:
        raise ValueError("TRUST_POLICY_SCOPE")
    out={};pubs=set()
    for k in doc["keys"]:
        exact(k,("key_id","organization","origin","role","public_key_hex","valid_from_utc","valid_until_utc"))
        kid,org,origin=map(name,(k["key_id"],k["organization"],k["origin"]))
        key=hexbytes(k["public_key_hex"],32);start,end=map(utc,(k["valid_from_utc"],k["valid_until_utc"]))
        if kid in out or key in pubs or k["role"] not in ROLES or not start<end:
            raise ValueError("TRUST_POLICY_KEY")
        pubs.add(key);out[kid]={**k,"key":key,"start":start,"end":end}
    return out

def verify_signature(public_key,message,signature):
    # OpenSSL performs Ed25519 verification; no shell, no remote lookup.
    with tempfile.TemporaryDirectory() as d:
        p=Path(d);(p/"key.der").write_bytes(DER_PREFIX+public_key)
        (p/"message").write_bytes(DOMAIN+message);(p/"signature").write_bytes(signature)
        try:
            q=subprocess.run(["openssl","pkeyutl","-verify","-pubin","-keyform","DER",
                "-inkey",str(p/"key.der"),"-rawin","-in",str(p/"message"),"-sigfile",str(p/"signature")],
                capture_output=True,timeout=5,check=False)
        except (OSError,subprocess.TimeoutExpired) as exc:
            raise ValueError("SIGNATURE_BACKEND_UNAVAILABLE") from exc
        if q.returncode:raise ValueError("SIGNATURE_INVALID")

def signed(payload,signature_hex,policy,role,as_of):
    bounded(payload,MAX_RECEIPT);r=decode(payload)
    if type(r) is not dict:raise ValueError("RECEIPT_FIELDS")
    k=policy.get(r.get("key_id"))
    if k is None or k["role"]!=role or r.get("origin")!=k["origin"]:raise ValueError("SIGNER_NOT_AUTHORIZED")
    stamp=utc(r["signed_utc"])
    if not k["start"]<=stamp<k["end"] or stamp>as_of:raise ValueError("SIGNER_CLOCK")
    verify_signature(k["key"],payload,hexbytes(signature_hex,64))
    return r,k,stamp

def audit_fixture(archive,policy_raw,policy_sha256,witness,results,*,fixture_id,as_of_utc):
    """One fixture from existing BL1 archive; signatures over exact bytes.
    witness=(receipt_bytes,signature_hex); results=[(receipt_bytes,signature_hex,raw_bytes),...].
    No source adapter or external witness service is called.
    """
    as_of=utc(as_of_utc);mid=native(fixture_id)
    bounded(archive,MAX_RAW);archive_sha=sha(archive);policy=trust_policy(policy_raw,policy_sha256)
    w,wk,wt=signed(*witness,policy,"witness",as_of)
    exact(w,("schema","key_id","origin","signed_utc","archive_sha256"))
    if w["schema"]!="v20-archive-witness-v1" or w["archive_sha256"]!=archive_sha:raise ValueError("WITNESS_BINDING")
    record,proof=audit(archive,archive_sha,wt)
    match=[r for r in record["rows"] if r["provider_event_id"]==mid]
    if len(match)!=1:raise ValueError("FIXTURE_NOT_SEALED")
    r=match[0];ko=utc(r["kickoff_utc"])
    if not wt<ko-timedelta(minutes=10):raise ValueError("LATE_WITNESS")
    if type(results) is not list or len(results)!=2:raise ValueError("RESULT_COUNT")
    identities={(wk["organization"].casefold(),wk["origin"].casefold())};orgs={wk["organization"].casefold()};origins={wk["origin"].casefold()}
    scores=[];hashes=[];ids=[]
    for payload,sig,raw in results:
        bounded(raw,MAX_RAW)
        q,k,t=signed(payload,sig,policy,"result",as_of)
        exact(q,("schema","key_id","origin","signed_utc","archive_sha256","fixture_id","home_native_id",
                 "away_native_id","kickoff_utc","observed_utc","raw_sha256","scope","status","home_goals","away_goals"))
        if q["schema"]!="v20-result-receipt-v1" or q["archive_sha256"]!=archive_sha or q["fixture_id"]!=mid or q["home_native_id"]!=r["home_native_id"] or q["away_native_id"]!=r["away_native_id"] or utc(q["kickoff_utc"])!=ko:
            raise ValueError("RESULT_BINDING")
        if k["organization"].casefold() in orgs or k["origin"].casefold() in origins:raise ValueError("RESULT_ORIGIN_CONFLICT")
        orgs.add(k["organization"].casefold());origins.add(k["origin"].casefold())
        if not ko+timedelta(minutes=90)<=utc(q["observed_utc"])<=t<=as_of:
            raise ValueError("RESULT_CLOCK")
        if q["scope"]!="FULL_MATCH_REGULATION" or q["status"]!="FINISHED" or q["raw_sha256"]!=sha(raw):
            raise ValueError("RESULT_SCOPE_OR_RAW_HASH")
        score=(q["home_goals"],q["away_goals"])
        if any(type(x) is not int or not 0<=x<=20 for x in score):raise ValueError("RESULT_SCORE")
        scores.append(score);hashes.append(sha(raw));ids.append(k["key_id"])
    if scores[0]!=scores[1] or hashes[0]==hashes[1]:raise ValueError("RESULT_CONFLICT")
    h,a=scores[0];y=0 if h>a else 1 if h==a else 2
    case={"y":y,"baseline":vec(r["baseline"]),"candidate":vec(r["candidate"])}
    return {"schema":"v20-signed-receipt-research-v1","fixture_id":mid,"archive_sha256":archive_sha,
            "trust_policy_sha256":policy_sha256,"witness_signed_utc":wt.isoformat(),"witness_key_id":wk["key_id"],
            "result_signer_ids":ids,"result_raw_sha256":hashes,"claimed_final_score":[h,a],
            "baseline":metrics([case],lambda x:x["baseline"]),"candidate":metrics([case],lambda x:x["candidate"]),
            "signature_checks_passed":True,"declared_distinct_organizations":True,
            "upstream_payload_semantics_independently_verified":False,"external_trust_policy_provenance_verified":False,
            "actual_source_independence_verified":False,"trusted_clock_independently_verified":False,
            "verified_forward_sample_credit":0,"verified_ev":False,"automatic_promotion":False,
            "production_recommendations":"DISABLED","status":"HOLD"}
