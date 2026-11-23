"""Deterministic, private-only in-memory replay package for *untrusted* live claims.

Stores the EXACT two caller-supplied normalized JSON bytes, rather than only
their SHA256. This module performs no network request or durable disk write.
The returned tar bytes may contain confidential URLs and MUST NOT be uploaded
to public GitHub, logged, attached to PRs or sent to a public dashboard.

This does NOT prove that any provider issued the payload, source independence,
an external timestamp, actual live collection, model calibration, or EV.
"""
import hashlib
import io
import json
import tarfile
from datetime import datetime, timezone

from inplay_two_source_byte_packet import (
    audit as audit_claims, _decode, _canonical, _utc,
)

SCHEMA="football-king-private-inplay-claim-replay-v1"
MAX_PACKAGE_BYTES=131_072
MAX_SINGLE_FILE_BYTES=12_000
MAX_FILES=3
_ALLOWED_PROVIDERS=frozenset(("fotmob","sofascore","flashscore"))


def _require(condition,reason):
    if not condition:
        raise ValueError(reason)


def _clock(now):
    current=datetime.now(timezone.utc) if now is None else now
    _require(isinstance(current,datetime) and current.tzinfo is not None
             and current.utcoffset() is not None, "INVALID_PRIVATE_REPLAY_CLOCK")
    return current.astimezone(timezone.utc)


def _manifest(fixture, claims, sampled_at, packet_sha):
    return {
        "schema":SCHEMA,
        "private_only":True,
        "fixture_claim":fixture,
        "local_audit_utc_self_claimed":sampled_at.isoformat(),
        "packet_sha256_unattested":packet_sha,
        "files":[
            {"name":name, "sha256":hashlib.sha256(data).hexdigest(),"bytes":len(data)}
            for name,data in claims.items()
        ],
    }


def _tar(files):
    _require(set(files)==set(files), "INVALID_PACKAGE_MEMBERS")
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode="w",format=tarfile.USTAR_FORMAT) as archive:
        for name in ["manifest.json"]+sorted(n for n in files if n!="manifest.json"):
            raw=files[name]
            _require(type(raw) is bytes and 0<len(raw)<=MAX_SINGLE_FILE_BYTES,
                     "INVALID_PRIVATE_PACKAGE_FILE")
            member=tarfile.TarInfo(name)
            member.mode=0o600
            member.mtime=0
            member.uid=member.gid=0
            member.uname=member.gname=""
            member.size=len(raw)
            archive.addfile(member,io.BytesIO(raw))
    data=out.getvalue()
    _require(len(data)<=MAX_PACKAGE_BYTES, "PRIVATE_PACKAGE_TOO_LARGE")
    return data


def make_private_package(fixture, raw_claims, *, now=None):
    """Produce portable *private* bytes; caller must separately store securely.

    No file is archived durably here. A successful package remains unverified
    research. Never call with raw commercial data without confirmed licensing.
    """
    current=_clock(now)
    report=audit_claims(fixture,raw_claims,now=current)
    _require(report["status"]=="RESEARCH_ONLY","SOURCE_CLAIMS_NOT_ADMISSIBLE")
    by_name={}
    for item in raw_claims:
        decoded=_decode(item)
        provider=decoded["provider"]
        _require(provider in _ALLOWED_PROVIDERS,"UNKNOWN_CLAIM_PUBLISHER")
        filename=provider+".claim.json"
        _require(filename not in by_name,"DUPLICATE_CLAIM_PUBLISHER")
        by_name[filename]=item
    by_name=dict(sorted(by_name.items()))
    envelope=_manifest(fixture,by_name,current,report["packet_sha256_unattested"])
    files={"manifest.json":_canonical(envelope),**by_name}
    return _tar(files)


def _replay_members(raw):
    _require(type(raw) is bytes and 0<len(raw)<=MAX_PACKAGE_BYTES,
             "INVALID_OR_OVERSIZED_PRIVATE_PACKAGE")
    try:
        with tarfile.open(fileobj=io.BytesIO(raw),mode="r:") as archive:
            entries=archive.getmembers()
            _require(len(entries)==MAX_FILES, "INVALID_PRIVATE_MEMBER_COUNT")
            result={}
            for member in entries:
                name=member.name
                _require(name=="manifest.json" or name in
                         {p+".claim.json" for p in _ALLOWED_PROVIDERS},
                         "INVALID_PRIVATE_MEMBER_NAME")
                _require(name not in result and member.isfile()
                         and member.size>0 and member.size<=MAX_SINGLE_FILE_BYTES
                         and member.uid==0 and member.gid==0 and member.mtime==0
                         and member.mode==0o600 and not member.uname
                         and not member.gname and not member.linkname,
                         "INVALID_PRIVATE_MEMBER_HEADER")
                stream=archive.extractfile(member)
                _require(stream is not None,"INVALID_PRIVATE_MEMBER")
                data=stream.read(MAX_SINGLE_FILE_BYTES+1)
                _require(len(data)==member.size,"INVALID_PRIVATE_MEMBER_CONTENT")
                result[name]=data
    except (tarfile.TarError,OSError,EOFError):
        raise ValueError("INVALID_PRIVATE_PACKAGE_FORMAT") from None
    _require("manifest.json" in result,"PRIVATE_MANIFEST_MISSING")
    _require(_tar(result)==raw,"NONDETERMINISTIC_OR_TRAILING_PRIVATE_PACKAGE")
    return result


def _parse_manifest(raw):
    def pairs(items):
        out={}
        for key,value in items:
            _require(key not in out,"DUPLICATE_PRIVATE_MANIFEST_FIELD")
            out[key]=value
        return out
    def reject(_):
        raise ValueError("NONFINITE_PRIVATE_MANIFEST_VALUE")
    try:
        value=json.loads(raw.decode("utf-8"),object_pairs_hook=pairs,
                         parse_constant=reject)
    except (UnicodeError,json.JSONDecodeError,RecursionError):
        raise ValueError("INVALID_PRIVATE_MANIFEST") from None
    _require(type(value) is dict and set(value)=={
        "schema","private_only","fixture_claim","local_audit_utc_self_claimed",
        "packet_sha256_unattested","files"} and value["schema"]==SCHEMA
        and value["private_only"] is True,
        "INVALID_PRIVATE_MANIFEST")
    _require(_canonical(value)==raw,"NONCANONICAL_PRIVATE_MANIFEST")
    return value


def _hold(reason):
    return {
        "schema":SCHEMA,"status":"HOLD","reason":reason,
        "exact_original_claim_bytes_replayed":False,
        "deterministic_private_container_rebuilt":False,
        "private_package_sha256_unattested":None,
        "packet_sha256_unattested":None,
        "source_byte_sha256_unattested":[],
        "claimed_source_count":0,
        "raw_source_publisher_authenticated":False,
        "source_independence_verified":False,
        "externally_attested":False,
        "durable_storage_verified":False,
        "eligible_for_model_input":False,
        "eligible_for_model_scoring":False,
        "positive_ev_verified":False,
        "certified_forward_samples":0,
        "production_recommendations":"DISABLED",
        "recommendation":None,"roi":None,
    }


def replay_private_package(package, *, now=None):
    """Replay untrusted original claimed bytes without disclosing their content.

    The self-reported audit timestamp may be from any past date and is NOT
    independently trusted. Replay later must not falsely mark data 'stale'
    relative to its historical decision. A capture in the future is rejected.
    """
    try:
        current=_clock(now)
        files=_replay_members(package)
        manifest=_parse_manifest(files["manifest.json"])
        claimed_time=_utc(manifest["local_audit_utc_self_claimed"])
        _require(current>=claimed_time,"FUTURE_PRIVATE_AUDIT_CLAIM")
        descriptions=manifest["files"]
        _require(type(descriptions) is list and len(descriptions)==2,
                 "INVALID_PRIVATE_FILE_DESCRIPTORS")
        names=[x.get("name") for x in descriptions if type(x) is dict]
        _require(len(names)==2 and names==sorted(names)
                 and set(names)==set(files)-{"manifest.json"},
                 "PRIVATE_CLAIM_FILE_LIST_MISMATCH")
        for descriptor in descriptions:
            data=files[descriptor["name"]]
            _require(set(descriptor)=={"name","sha256","bytes"}
                     and type(descriptor["bytes"]) is int
                     and descriptor["bytes"]==len(data)
                     and descriptor["sha256"]==hashlib.sha256(data).hexdigest(),
                     "PRIVATE_CLAIM_BYTES_CHANGED")
        raw_claims=[files[name] for name in names]
        checked=audit_claims(manifest["fixture_claim"],raw_claims,now=claimed_time)
        _require(checked["status"]=="RESEARCH_ONLY"
                 and checked["packet_sha256_unattested"]==manifest["packet_sha256_unattested"],
                 "PRIVATE_PACKET_REPLAY_MISMATCH")
        return {
            **_hold("EXACT_BYTES_REPLAYED_NOT_EXTERNAL_PROVENANCE"),
            "status":"RESEARCH_ONLY",
            "exact_original_claim_bytes_replayed":True,
            "deterministic_private_container_rebuilt":True,
            "private_package_sha256_unattested":hashlib.sha256(package).hexdigest(),
            "packet_sha256_unattested":checked["packet_sha256_unattested"],
            "source_byte_sha256_unattested":checked["source_byte_sha256_unattested"],
            "claimed_source_count":2,
            "original_claim_bytes_in_private_package":True,
            "archive_persistence_performed_by_this_module":False,
            "local_audit_utc_self_claimed":claimed_time.isoformat(),
        }
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError):
        # Fixed public-safe reason. Never echo original URL, raw source
        # bytes, file locations, tokens or arbitrary exception text.
        return _hold("INVALID_OR_TAMPERED_PRIVATE_CLAIM_PACKAGE")
