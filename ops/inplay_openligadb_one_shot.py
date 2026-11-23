"""Manual one-shot OpenLigaDB raw HTTP capture into private local archive.

ONE GET for ONE explicitly supplied native match ID, no schedule/retry/poll.
OpenLigaDB ODbL 1.0 and API access terms: openligadb.de/en/license and
openligadb.de/en/terms-of-use (07 Nov 2026). Respect per-league pacing,
use cheap getlastchangedate for any FUTURE scheduled integration, and provide
attribution. Never redistribute third-party image/logo URLs.

The exact received HTTP body (not normalized claim JSON) and locally generated
HTTP receipt are stored inside one create-only 0600 USTAR in a preprovisioned
0700 private directory, outside git. Research-only, no independent validation,
TSA, red-card coverage, bookmaker odds, xG, EV, scoring or betting.
"""
import hashlib
import io
import json
import os
import re
import tarfile
from datetime import datetime, timezone, timedelta
from urllib.request import Request, HTTPRedirectHandler, build_opener

from ops import private_response_capture as private
from ops.shadow_raw_source_collector import strict_json_loads
from inplay_private_local_store import _root_fd

SCHEMA="football-king-openligadb-one-shot-raw-private-v1"
BASE="https://api.openligadb.de/getmatchdata/"
MAX_BODY=250_000
MAX_ARCHIVE=524_288
ALLOWED_TYPES={"application/json","text/json","text/plain"}
MAX_DURATION=timedelta(seconds=30)
ATTRIBUTION="Data from OpenLigaDB (www.openligadb.de), licensed under ODbL 1.0"
PIN=re.compile(r"[0-9a-f]{64}\Z")


class RefuseRedirect(HTTPRedirectHandler):
    def redirect_request(self,*_):
        return None


def _fail(reason):
    raise ValueError(reason)


def _utc(value):
    if type(value) is not str or len(value)>70:
        _fail("INVALID_UTC")
    try:
        val=datetime.fromisoformat(value.replace("Z","+00:00"))
        if val.tzinfo is None or val.utcoffset() is None:
            _fail("INVALID_UTC")
        return val.astimezone(timezone.utc)
    except (ValueError,TypeError,OverflowError):
        _fail("INVALID_UTC")


def _now(clock):
    v=(datetime.now(timezone.utc) if clock is None else
       clock() if callable(clock) else clock)
    if not isinstance(v,datetime) or v.tzinfo is None or v.utcoffset() is None:
        _fail("INVALID_LOCAL_CAPTURE_CLOCK")
    return v.astimezone(timezone.utc)


def _endpoint(match_id):
    if type(match_id) is not int or not 1<=match_id<=999_999_999:
        _fail("INVALID_MATCH_ID")
    return BASE+str(match_id)


def _fetch_one(url):
    if type(url) is not str or not url.startswith(BASE):
        _fail("INVALID_ENDPOINT")
    suffix=url[len(BASE):]
    if not suffix.isascii() or not suffix.isdigit() or str(int(suffix))!=suffix:
        _fail("INVALID_ENDPOINT")
    req=Request(url,method="GET",headers={
        "Accept":"application/json,text/json,text/plain",
        "User-Agent":"FootballKingResearch/0.1 (+https://github.com/CHANCHUNWA1989/football-king-report/issues)",
    })
    with build_opener(RefuseRedirect()).open(req,timeout=15) as reply:
        status=reply.status
        media=reply.headers.get("Content-Type","")
        final=reply.geturl()
        raw=reply.read(MAX_BODY+1)
        return (raw,status,media,final)


def _validate_raw(raw,match_id,seen_at):
    if type(raw) is not bytes or not 1<=len(raw)<=MAX_BODY:
        _fail("INVALID_HTTP_BODY")
    try:
        item=strict_json_loads(raw)
    except (ValueError,UnicodeError,TypeError,RecursionError,OverflowError):
        _fail("INVALID_SOURCE_JSON")
    if type(item) is not dict or (type(item.get("matchID")) is not int
            or item["matchID"]!=match_id
            or item.get("leagueShortcut")!="bl1"
            or type(item.get("leagueSeason")) is not int
            or not 2020<=item["leagueSeason"]<=2100
            or item.get("matchIsFinished") is not False):
        _fail("NOT_EXACT_UNFINISHED_BUNDESLIGA_FIXTURE")
    first,second=item.get("team1"),item.get("team2")
    if (type(first) is not dict or type(second) is not dict
            or any(type(x.get("teamId")) is not int or x["teamId"]<=0
                   for x in (first,second))
            or first["teamId"]==second["teamId"]):
        _fail("MISSING_UNAMBIGUOUS_NATIVE_TEAMS")
    ko=_utc(item.get("matchDateTimeUTC"))
    if not timedelta(0)<=seen_at-ko<=timedelta(hours=3):
        _fail("NOT_CURRENT_MATCH_CLOCK")
    # Do not infer red cards or score from optional goals/results. They can be
    # delayed and the upstream community data has no editorial verification.
    return item


def _canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,
                      separators=(",",":"),allow_nan=False).encode("utf-8")


def _tar(parts):
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode="w",format=tarfile.USTAR_FORMAT) as archive:
        for name in ("receipt.json","response.json"):
            value=parts[name]
            member=tarfile.TarInfo(name)
            member.size=len(value)
            member.mtime=member.uid=member.gid=0
            member.mode=0o600
            member.uname=member.gname=""
            archive.addfile(member,io.BytesIO(value))
    result=out.getvalue()
    if len(result)>MAX_ARCHIVE:
        _fail("ARCHIVE_SIZE_LIMIT")
    return result


def _unpack(raw):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_ARCHIVE:
        _fail("INVALID_ARCHIVE")
    try:
        with tarfile.open(fileobj=io.BytesIO(raw),mode="r:") as archive:
            members=archive.getmembers()
            if [x.name for x in members]!=["receipt.json","response.json"]:
                _fail("BAD_ARCHIVE_MEMBERS")
            files={}
            for member in members:
                if (not member.isfile() or member.mode!=0o600
                        or member.uid!=0 or member.gid!=0 or member.mtime!=0
                        or member.linkname or member.uname or member.gname
                        or not 0<member.size<=MAX_BODY):
                    _fail("BAD_ARCHIVE_MEMBER")
                stream=archive.extractfile(member)
                if stream is None:
                    _fail("BAD_ARCHIVE_MEMBER")
                body=stream.read(MAX_BODY+1)
                if len(body)!=member.size:
                    _fail("BAD_ARCHIVE_SIZE")
                files[member.name]=body
    except (tarfile.TarError,OSError,EOFError):
        _fail("INVALID_ARCHIVE")
    if _tar(files)!=raw:
        _fail("NONCANONICAL_ARCHIVE")
    try:
        receipt=strict_json_loads(files["receipt.json"])
    except (ValueError,UnicodeError,RecursionError,OverflowError):
        _fail("INVALID_RECEIPT_JSON")
    if (type(receipt) is not dict or set(receipt)!={
        "schema","source_url","match_id","requested_utc","completed_utc",
        "content_type","http_status","raw_sha256","raw_bytes",
        "source_single_unverified","production_recommendations","attribution"}
            or receipt.get("schema")!=SCHEMA
            or receipt.get("attribution")!=ATTRIBUTION
            or receipt.get("source_single_unverified") is not True
            or receipt.get("production_recommendations")!="DISABLED"
            or type(receipt.get("match_id")) is not int):
        _fail("INVALID_CAPTURE_RECEIPT")
    match_id=receipt["match_id"]
    if (receipt.get("source_url")!=_endpoint(match_id)
            or receipt.get("content_type") not in ALLOWED_TYPES
            or type(receipt.get("http_status")) is not int
            or receipt["http_status"]!=200
            or type(receipt.get("raw_bytes")) is not int
            or receipt["raw_bytes"]!=len(files["response.json"])
            or receipt.get("raw_sha256")!=hashlib.sha256(files["response.json"]).hexdigest()
            or _canonical(receipt)!=files["receipt.json"]):
        _fail("RECEIPT_RAW_BINDING_MISMATCH")
    started,ended=_utc(receipt["requested_utc"]),_utc(receipt["completed_utc"])
    if not timedelta(0)<=ended-started<=MAX_DURATION:
        _fail("INVALID_CAPTURE_CLOCK_ORDER")
    _validate_raw(files["response.json"],match_id,ended)
    return receipt,files["response.json"]


def _report(reason="RAW_CAPTURE_NOT_VERIFIED"):
    return {
        "schema":SCHEMA,"status":"HOLD","reason":reason,
        "local_original_response_bytes_readback_verified":False,
        "created_new_private_archive":False,
        "source_raw_sha256_unattested":None,
        "archive_sha256_unattested":None,
        "transport_externally_attested":False,
        "publisher_identity_authenticated":False,
        "two_source_independence_verified":False,
        "actual_live_score_verified":False,
        "red_cards_available":False,
        "odds_or_xg_verified":False,
        "eligible_for_model_input":False,
        "eligible_for_model_scoring":False,
        "model_probability":None,
        "positive_ev_verified":False,
        "certified_forward_samples":0,
        "durable_storage_independently_verified":False,
        "production_recommendations":"DISABLED",
        "recommendation":None,"roi":None,
        "source_attribution":ATTRIBUTION,
    }


def _read_archive(descriptor,name,digest):
    raw=private._read(descriptor,name,MAX_ARCHIVE)
    if hashlib.sha256(raw).hexdigest()!=digest:
        _fail("PRIVATE_ARCHIVE_CHANGED")
    receipt,payload=_unpack(raw)
    return receipt,payload


def capture_once(match_id,private_root,*,getter=None,now=None):
    """Manual explicit one-off GET, no retry, no periodic polling, no secrets.

    The optional getter and now callbacks exist for no-network synthetic tests.
    In production the default GET makes one request to the exact official API
    endpoint. Success proves local byte preservation only; never live truth.
    """
    descriptor=None
    try:
        url=_endpoint(match_id)
        descriptor=_root_fd(private_root)  # refuse public or Git repo path before GET
        started=_now(now)
        request=_fetch_one if getter is None else getter
        response=request(url)
        ended=_now(now)
        if (type(response) is not tuple or len(response)!=4
                or not timedelta(0)<=ended-started<=MAX_DURATION):
            _fail("INVALID_FETCH_RESULT_OR_CLOCK")
        raw,status,media,final=response
        if (type(status) is not int or status!=200
                or type(final) is not str or final!=url
                or type(media) is not str
                or media.split(";",1)[0].strip().lower() not in ALLOWED_TYPES):
            _fail("INVALID_HTTP_ORIGIN_RECEIPT")
        mime=media.split(";",1)[0].strip().lower()
        _validate_raw(raw,match_id,ended)
        receipt={"schema":SCHEMA,"source_url":url,"match_id":match_id,
                 "requested_utc":started.isoformat(),
                 "completed_utc":ended.isoformat(),
                 "content_type":mime,"http_status":200,
                 "raw_sha256":hashlib.sha256(raw).hexdigest(),
                 "raw_bytes":len(raw),
                 "source_single_unverified":True,
                 "production_recommendations":"DISABLED",
                 "attribution":ATTRIBUTION}
        package=_tar({"receipt.json":_canonical(receipt),"response.json":raw})
        expected=hashlib.sha256(package).hexdigest()
        name="openligadb-bl1-"+expected+".tar"
        created=False
        try:
            os.stat(name,dir_fd=descriptor,follow_symlinks=False)
        except FileNotFoundError:
            fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,
                       0o600,dir_fd=descriptor)
            with os.fdopen(fd,"wb") as stream:
                stream.write(package)
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(descriptor)
            created=True
        recovered_receipt,recovered_raw=_read_archive(descriptor,name,expected)
        if recovered_receipt!=receipt or recovered_raw!=raw:
            _fail("SINGLE_SOURCE_READBACK_MISMATCH")
        return {**_report("SINGLE_UNVERIFIED_OPENLIGA_RAW_CAPTURED"),
                "status":"RESEARCH_ONLY",
                "local_original_response_bytes_readback_verified":True,
                "created_new_private_archive":created,
                "source_raw_sha256_unattested":receipt["raw_sha256"],
                "archive_sha256_unattested":expected}
    except Exception:
        # Do not print response body, HTML errors, filenames or provider content.
        return _report("INVALID_OR_UNAVAILABLE_ONE_SHOT_CAPTURE")
    finally:
        if descriptor is not None:
            os.close(descriptor)


def replay_saved(private_root,expected_digest,*,now=None):
    """Read private one-shot archive by exact digest, without any HTTP access."""
    descriptor=None
    try:
        if type(expected_digest) is not str or PIN.fullmatch(expected_digest) is None:
            _fail("INVALID_ARCHIVE_PIN")
        current=_now(now)
        descriptor=_root_fd(private_root)
        receipt,body=_read_archive(descriptor,"openligadb-bl1-"+expected_digest+".tar",expected_digest)
        if _utc(receipt["completed_utc"])>current:
            _fail("CAPTURE_IS_IN_FUTURE")
        return {**_report("LOCAL_SINGLE_SOURCE_REPLAY_NOT_ATTESTED"),
                "status":"RESEARCH_ONLY",
                "local_original_response_bytes_readback_verified":True,
                "source_raw_sha256_unattested":hashlib.sha256(body).hexdigest(),
                "archive_sha256_unattested":expected_digest}
    except Exception:
        return _report("PRIVATE_ONE_SHOT_REPLAY_UNAVAILABLE")
    finally:
        if descriptor is not None:
            os.close(descriptor)


def main(argv=None):
    """Manual operation only; the command does not create a destination."""
    import argparse
    parser=argparse.ArgumentParser(description="One explicit OpenLigaDB match GET, private research")
    parser.add_argument("--match-id",type=int,required=True)
    parser.add_argument("--private-root",required=True)
    parser.add_argument("--manual-one-shot",action="store_true",required=True)
    args=parser.parse_args(argv)
    # Manual CLI MUST go through the shared-host league pacing gate.
    # Low-level capture_once remains available solely for injected unit tests
    # and for future audited orchestration; do not schedule it directly.
    from inplay_openligadb_league_pacing import paced_capture_once
    report=paced_capture_once(args.match_id,args.private_root)
    print(json.dumps(report,ensure_ascii=False,sort_keys=True,allow_nan=False))
    raise SystemExit(0 if report["status"]=="RESEARCH_ONLY" else 2)


if __name__=="__main__":
    main()
