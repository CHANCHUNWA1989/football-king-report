"""Manual OpenLigaDB lastchangedate probe using the *same* bl1 league gate.

This probes exactly one season/matchday at a time, with one GET at most.
The token is a provider-provided timestamp *string*, sometimes timezone-naive;
it is used only for string equality, NEVER as verified provider issue time.
The first successful response establishes a baseline; a difference later is
an unverified signal, NOT authorization to fetch a match automatically.

One POSIX host + one 0700 private root share PR542's flock and 90s/600s
cooldown with full match GETs. No scheduling, retry, distributed coordination,
source verification, live scoring, xG, odds, EV or promotions.
"""
import base64
import hashlib
import json
import os
import re
import stat
from datetime import datetime, timedelta, timezone
from urllib.request import Request, build_opener

from ops.shadow_raw_source_collector import strict_json_loads
from inplay_private_local_store import _root_fd
from inplay_openligadb_one_shot import _now, _utc, RefuseRedirect
from inplay_openligadb_league_pacing import (
    _open_locked_state, _read_state, _write_state,
    COOLDOWN_SUCCESS, COOLDOWN_FAILURE,
)

PROBE_SCHEMA="football-king-openligadb-lastchangedate-probe-v1"
PROBE_FILE=".openligadb-bl1-lastchange.json"
ENDPOINT="https://api.openligadb.de/getlastchangedate/bl1/"
MAX_RESPONSE=256
MAX_CHECKPOINT=1024
MEDIA={"text/plain","text/json","application/json"}
PATTERN=re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,7})?(?:Z|[+-][0-9]{2}:[0-9]{2})?\Z")
FIELDS={"schema","season","group_order_id","raw_response_base64",
        "raw_response_sha256","token_sha256","observed_utc"}


class ProbeFailure(ValueError):
    """Safe error code; never disclose response body or untrusted URL."""


def _reject(reason):
    raise ProbeFailure(reason)


def _probe_url(season,group):
    if (type(season) is not int or not 2020<=season<=2100
            or type(group) is not int or not 1<=group<=34):
        _reject("INVALID_SEASON_OR_GROUP")
    return ENDPOINT+str(season)+"/"+str(group)


def _parse_token(raw):
    if type(raw) is not bytes or not 1<=len(raw)<=MAX_RESPONSE:
        _reject("BAD_CHANGE_RESPONSE_BYTES")
    try:
        value=strict_json_loads(raw)
        if (type(value) is not str or not 19<=len(value)<=45
                or PATTERN.fullmatch(value) is None):
            _reject("BAD_CHANGE_TOKEN_STRING")
        # Parse validity only. DateTime unspecified by publisher has NO
        # assured timezone, and no relation to local capture time is inferred.
        parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
        if not 2000<=parsed.year<=2100:
            _reject("BAD_CHANGE_TOKEN_STRING")
    except (ValueError,TypeError,UnicodeError,OverflowError,RecursionError):
        _reject("BAD_CHANGE_TOKEN_STRING")
    return value


def _fetch_one(url):
    if type(url) is not str or url!=_probe_url_from_url(url):
        _reject("INVALID_CHANGE_PROBE_ENDPOINT")
    req=Request(url,method="GET",headers={
        "Accept":"application/json,text/json,text/plain",
        "User-Agent":"FootballKingResearch/0.1 (+https://github.com/CHANCHUNWA1989/football-king-report/issues)",
    })
    with build_opener(RefuseRedirect()).open(req,timeout=15) as response:
        body=response.read(MAX_RESPONSE+1)
        return body,response.status,response.headers.get("Content-Type",""),response.geturl()


def _probe_url_from_url(url):
    # No arbitrary host, extra path, query or redirects.
    if not url.startswith(ENDPOINT):
        _reject("INVALID_CHANGE_PROBE_ENDPOINT")
    pieces=url[len(ENDPOINT):].split("/")
    if len(pieces)!=2 or any(not p.isascii() or not p.isdigit() or not p or p.startswith("0") for p in pieces):
        _reject("INVALID_CHANGE_PROBE_ENDPOINT")
    return _probe_url(int(pieces[0]),int(pieces[1]))


def _validated_response(value,expected_url):
    if type(value) is not tuple or len(value)!=4:
        _reject("INVALID_CHANGE_HTTP_RESPONSE")
    body,status,content_type,final_url=value
    if (type(status) is not int or status!=200
            or type(content_type) is not str
            or content_type.split(";",1)[0].strip().lower() not in MEDIA
            or type(final_url) is not str or final_url!=expected_url):
        _reject("INVALID_CHANGE_HTTP_RESPONSE")
    return _parse_token(body),body


def _encode(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,
                      separators=(",",":"),allow_nan=False).encode("utf-8")


def _checkpoint_value(season,group,raw,token,at):
    return {"schema":PROBE_SCHEMA,"season":season,"group_order_id":group,
            "raw_response_base64":base64.b64encode(raw).decode("ascii"),
            "raw_response_sha256":hashlib.sha256(raw).hexdigest(),
            "token_sha256":hashlib.sha256(token.encode("utf-8")).hexdigest(),
            "observed_utc":at.isoformat()}


def _validate_checkpoint(raw,season,group):
    if not raw or len(raw)>MAX_CHECKPOINT:
        _reject("INVALID_PRIVATE_CHANGE_CHECKPOINT")
    try:
        row=strict_json_loads(raw)
        if type(row) is not dict or set(row)!=FIELDS or row.get("schema")!=PROBE_SCHEMA:
            _reject("INVALID_PRIVATE_CHANGE_CHECKPOINT")
        if row.get("season")!=season or row.get("group_order_id")!=group:
            _reject("MISMATCHED_PRIVATE_CHANGE_GROUP")
        if (type(row.get("raw_response_base64")) is not str
                or len(row["raw_response_base64"])>350
                or type(row.get("raw_response_sha256")) is not str
                or type(row.get("token_sha256")) is not str):
            _reject("INVALID_PRIVATE_CHANGE_CHECKPOINT")
        body=base64.b64decode(row["raw_response_base64"],validate=True)
        token=_parse_token(body)
        if (hashlib.sha256(body).hexdigest()!=row["raw_response_sha256"]
                or hashlib.sha256(token.encode()).hexdigest()!=row["token_sha256"]
                or _encode(row)!=raw):
            _reject("INVALID_PRIVATE_CHANGE_CHECKPOINT")
        _utc(row["observed_utc"])
        return row
    except ProbeFailure:
        raise
    except (ValueError,TypeError,KeyError,UnicodeError,OverflowError,RecursionError):
        _reject("INVALID_PRIVATE_CHANGE_CHECKPOINT")


def _read_checkpoint(dirfd,season,group):
    # The private response archive already supplies a symlink/hardlink-safe
    # owner 0600 bounded read with an inode/mode/version re-check.
    from ops.private_response_capture import _read
    try:
        raw=_read(dirfd,PROBE_FILE,MAX_CHECKPOINT)
    except FileNotFoundError:
        return None
    return _validate_checkpoint(raw,season,group)


def _verify_file(fd,dirfd):
    info=os.fstat(fd)
    link=os.stat(PROBE_FILE,dir_fd=dirfd,follow_symlinks=False)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid()
            or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)!=0o600
            or info.st_dev!=link.st_dev or info.st_ino!=link.st_ino
            or not stat.S_ISREG(link.st_mode) or info.st_size>MAX_CHECKPOINT):
        _reject("UNSAFE_PRIVATE_CHANGE_CHECKPOINT")
    return info


def _save_checkpoint(dirfd,old,season,group,raw,token,at):
    body=_encode(_checkpoint_value(season,group,raw,token,at))
    if len(body)>MAX_CHECKPOINT:
        _reject("CHANGE_CHECKPOINT_TOO_LARGE")
    fd=None
    try:
        if old is None:
            fd=os.open(PROBE_FILE,os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK|
                       os.O_CREAT|os.O_EXCL,0o600,dir_fd=dirfd)
        else:
            fd=os.open(PROBE_FILE,os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK,
                       dir_fd=dirfd)
        info=_verify_file(fd,dirfd)
        previous=os.pread(fd,MAX_CHECKPOINT+1,0)
        if old is None and previous!=b"":
            _reject("PRIVATE_CHANGE_STATE_RACE")
        if old is not None and previous!=_encode(old):
            _reject("PRIVATE_CHANGE_STATE_RACE")
        os.ftruncate(fd,0)
        total=0
        while total<len(body):
            n=os.write(fd,body[total:])
            if n<=0:
                _reject("CHANGE_CHECKPOINT_WRITE_FAILED")
            total+=n
        os.fsync(fd)
        os.fsync(dirfd)
        checked=_verify_file(fd,dirfd)
        if checked.st_size!=len(body):
            _reject("CHANGE_CHECKPOINT_WRITE_FAILED")
    finally:
        if fd is not None:
            os.close(fd)


def _report(reason="CHANGE_PROBE_NOT_ADMITTED",attempted=0):
    return {
        "schema":PROBE_SCHEMA,"status":"HOLD","reason":reason,
        "requests_attempted":attempted,
        "shared_host_league_pacing_applied":False,
        "centralized_across_hosts":False,
        "source_authenticated":False,
        "provider_token_timezone_authenticated":False,
        "provider_last_update_time_authenticated":False,
        "actual_match_updated_verified":False,
        "change_detected":None,
        "change_status":"HOLD",
        "raw_response_sha256_unattested":None,
        "source_token_sha256_unattested":None,
        "checkpoint_private_file_readback_verified":False,
        "full_match_get_performed":False,
        "eligible_for_full_match_auto_fetch":False,
        "eligible_for_model_input":False,
        "eligible_for_model_scoring":False,
        "externally_witnessed":False,
        "source_independence_verified":False,
        "positive_ev_verified":False,
        "certified_forward_samples":0,
        "production_recommendations":"DISABLED",
        "recommendation":None,"roi":None,
    }


def probe_once(season,group,private_root,*,getter=None,now=None):
    """One manual GET; persistent *single group* baseline in same league gate.

    Subsequent changed marker merely suggests a future manual capture after
    the 90s gate, never downloads a full response or upgrades model status.
    """
    dirfd=lockfd=None
    attempted=0
    try:
        url=_probe_url(season,group)
        dirfd=_root_fd(private_root)
        lockfd,was_new=_open_locked_state(dirfd)
        started=_now(now)
        old_rate=_read_state(lockfd,dirfd,was_new)
        checkpoint=_read_checkpoint(dirfd,season,group)
        if old_rate is not None:
            prior,limit=old_rate
            if started<prior:
                _reject("LOCAL_RATE_CLOCK_MOVED_BACKWARDS")
            if started<limit:
                _reject("SHARED_LEAGUE_RATE_WINDOW")
        if checkpoint is not None and started<_utc(checkpoint["observed_utc"]):
            _reject("LOCAL_PROBE_CLOCK_MOVED_BACKWARDS")
        _write_state(lockfd,dirfd,started,COOLDOWN_FAILURE,"RESERVED_OR_FAILED")
        attempted=1
        reply=(_fetch_one if getter is None else getter)(url)
        finished=_now(now)
        if not timedelta(0)<=finished-started<=timedelta(seconds=30):
            _reject("INVALID_CHANGE_PROBE_CLOCK")
        token,body=_validated_response(reply,url)
        prior_token=(None if checkpoint is None else
                     _parse_token(base64.b64decode(checkpoint["raw_response_base64"],validate=True)))
        changed=None if prior_token is None else (prior_token!=token)
        _save_checkpoint(dirfd,checkpoint,season,group,body,token,finished)
        # Verify exact private bytes after write, including canonical record.
        confirmed=_read_checkpoint(dirfd,season,group)
        if confirmed!=_checkpoint_value(season,group,body,token,finished):
            _reject("CHANGE_PROBE_LOCAL_READBACK_MISMATCH")
        _write_state(lockfd,dirfd,started,COOLDOWN_SUCCESS,"RESEARCH_ONLY")
        return {**_report("UNATTESTED_CHANGE_TOKEN_ONLY",attempted=1),
                "status":"RESEARCH_ONLY",
                "shared_host_league_pacing_applied":True,
                "change_detected":changed,
                "change_status":("BASELINE_ONLY" if changed is None else
                                 "CHANGED_UNATTESTED" if changed else "UNCHANGED"),
                "checkpoint_private_file_readback_verified":True,
                "raw_response_sha256_unattested":hashlib.sha256(body).hexdigest(),
                "source_token_sha256_unattested":hashlib.sha256(token.encode()).hexdigest()}
    except ProbeFailure as exc:
        return _report(str(exc),attempted=attempted)
    except Exception:
        return _report("INVALID_OR_UNAVAILABLE_CHANGE_PROBE",attempted=attempted)
    finally:
        if lockfd is not None:
            os.close(lockfd)
        if dirfd is not None:
            os.close(dirfd)


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description="Manual one-shot OpenLigaDB lastchangedate research probe")
    parser.add_argument("--season",type=int,required=True)
    parser.add_argument("--group-order",type=int,required=True)
    parser.add_argument("--private-root",required=True)
    parser.add_argument("--manual-probe",required=True,action="store_true")
    args=parser.parse_args(argv)
    report=probe_once(args.season,args.group_order,args.private_root)
    print(json.dumps(report,ensure_ascii=False,sort_keys=True,allow_nan=False))
    raise SystemExit(0 if report["status"]=="RESEARCH_ONLY" else 2)


if __name__=="__main__":
    main()
