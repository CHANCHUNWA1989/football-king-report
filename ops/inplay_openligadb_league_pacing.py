"""Shared-private-directory OpenLigaDB Bundesliga pacing, no autonomous poller.

Only the manual PR538 CLI is routed through this gate. A POSIX flock and a
0600 timestamp record jointly limit calls from cooperating local processes
using the SAME 0700 private directory on ONE POSIX host. There is NO claim
of cross-host, per-IP, distributed, upstream quota, or publisher identity
certification. Processes bypassing the wrapper are not rate limited.

Reserves a failure cooldown BEFORE the HTTP request. Crash or failed fetch
does not permit rapid retry. Successful capture reduces the embargo to a
conservative 90s per league; failed fetch retains 600s cooldown. Never
sleep, retry or schedule. OpenLigaDB usage terms must be rechecked before
deployment, especially getlastchangedate for any future repeat collector.
"""
import fcntl
import json
import os
import stat
from datetime import timedelta

from ops.shadow_raw_source_collector import strict_json_loads
from inplay_private_local_store import _root_fd
from inplay_openligadb_one_shot import _endpoint, _now, _utc, capture_once

SCHEMA="football-king-openligadb-shared-host-bl1-gate-v1"
RATE_FILE=".openligadb-bl1-pacing.json"
COOLDOWN_SUCCESS=90
COOLDOWN_FAILURE=600
MAX_STATE=512
KEYS={"schema","league","last_attempt_utc","not_before_utc","last_result"}


class PacingError(ValueError):
    """Sanitized fixed error code; no path, URL, raw data or request token."""


def _refuse(reason):
    raise PacingError(reason)


def _report(reason="REQUEST_NOT_ADMITTED", attempted=0):
    return {
        "schema":SCHEMA,"status":"HOLD","reason":reason,
        "shared_host_league_pacing_applied":False,
        "centralized_across_hosts":False,
        "requests_attempted":attempted,
        "min_success_interval_seconds":COOLDOWN_SUCCESS,
        "failed_request_cooldown_seconds":COOLDOWN_FAILURE,
        "source_authenticated":False,
        "source_independence_verified":False,
        "externally_witnessed":False,
        "original_response_readback_verified":False,
        "eligible_for_model_input":False,
        "eligible_for_model_scoring":False,
        "positive_ev_verified":False,
        "certified_forward_samples":0,
        "production_recommendations":"DISABLED",
        "recommendation":None,"roi":None,
    }


def _regular_rate_file(fd,dirfd):
    try:
        opened=os.fstat(fd)
        linked=os.stat(RATE_FILE,dir_fd=dirfd,follow_symlinks=False)
    except OSError:
        _refuse("UNSAFE_SHARED_RATE_STATE")
    if (not stat.S_ISREG(opened.st_mode) or opened.st_uid!=os.getuid()
            or stat.S_IMODE(opened.st_mode)!=0o600 or opened.st_nlink!=1
            or opened.st_size>MAX_STATE
            or opened.st_dev!=linked.st_dev or opened.st_ino!=linked.st_ino
            or not stat.S_ISREG(linked.st_mode)):
        _refuse("UNSAFE_SHARED_RATE_STATE")
    return opened


def _open_locked_state(dirfd):
    fd=None
    new=False
    flags=os.O_RDWR | os.O_NONBLOCK | os.O_NOFOLLOW
    try:
        try:
            fd=os.open(RATE_FILE,flags|os.O_CREAT|os.O_EXCL,0o600,dir_fd=dirfd)
            new=True
        except FileExistsError:
            fd=os.open(RATE_FILE,flags,dir_fd=dirfd)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            _refuse("SHARED_LEAGUE_GATE_BUSY")
        info=_regular_rate_file(fd,dirfd)
        if info.st_size==0 and not new:
            _refuse("EMPTY_OR_INTERRUPTED_RATE_RESERVATION")
        return fd,new
    except (OSError,PacingError):
        if fd is not None:
            os.close(fd)
        raise


def _read_state(fd,dirfd,was_new):
    info=_regular_rate_file(fd,dirfd)
    os.lseek(fd,0,os.SEEK_SET)
    raw=os.read(fd,MAX_STATE+1)
    after=_regular_rate_file(fd,dirfd)
    if (info.st_size!=len(raw) or info.st_size!=after.st_size
            or info.st_mtime_ns!=after.st_mtime_ns
            or info.st_ctime_ns!=after.st_ctime_ns):
        _refuse("SHARED_RATE_STATE_CHANGED")
    if was_new and raw==b"":
        return None
    if not raw or len(raw)>MAX_STATE:
        _refuse("INVALID_SHARED_RATE_STATE")
    try:
        value=strict_json_loads(raw)
        if (type(value) is not dict or set(value)!=KEYS
                or value["schema"]!=SCHEMA or value["league"]!="bl1"
                or value["last_result"] not in ("RESERVED_OR_FAILED","RESEARCH_ONLY")
                or _encode(value)!=raw):
            _refuse("INVALID_SHARED_RATE_STATE")
        attempt=_utc(value["last_attempt_utc"])
        not_before=_utc(value["not_before_utc"])
        if (not timedelta(0)<=not_before-attempt<=timedelta(seconds=COOLDOWN_FAILURE)):
            _refuse("INVALID_SHARED_RATE_STATE")
        if (value["last_result"]=="RESEARCH_ONLY"
                and not_before-attempt!=timedelta(seconds=COOLDOWN_SUCCESS)):
            _refuse("INVALID_SHARED_RATE_STATE")
    except (ValueError,TypeError,KeyError,UnicodeError,OverflowError,RecursionError):
        _refuse("INVALID_SHARED_RATE_STATE")
    return attempt,not_before


def _encode(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,
                      separators=(",",":"),allow_nan=False).encode("utf-8")


def _write_state(fd,dirfd,started,seconds,result):
    value={"schema":SCHEMA,"league":"bl1",
           "last_attempt_utc":started.isoformat(),
           "not_before_utc":(started+timedelta(seconds=seconds)).isoformat(),
           "last_result":result}
    raw=_encode(value)
    if not 0<len(raw)<=MAX_STATE:
        _refuse("SHARED_RATE_STATE_TOO_LARGE")
    _regular_rate_file(fd,dirfd)
    # Write under exclusive flock. Partial/damaged record will deliberately
    # fail closed in all later invocations, requiring operator inspection.
    os.lseek(fd,0,os.SEEK_SET)
    os.ftruncate(fd,0)
    total=0
    while total<len(raw):
        written=os.write(fd,raw[total:])
        if written<=0:
            _refuse("SHARED_RATE_STATE_WRITE_FAILED")
        total+=written
    os.fsync(fd)
    os.fsync(dirfd)
    final=_regular_rate_file(fd,dirfd)
    if final.st_size!=len(raw):
        _refuse("SHARED_RATE_STATE_WRITE_FAILED")


def paced_capture_once(match_id,private_root,*,getter=None,now=None):
    """Manual one request, shared single-host pacing, permanent research HOLD.

    Reserve before call. After failure cooldown 600s; after successful raw
    private readback 90s. Never retry, sleep, or fan out to extra API endpoints.
    """
    dirfd=ratefd=None
    attempted=0
    try:
        _endpoint(match_id)  # invalid IDs rejected before marker or GET
        dirfd=_root_fd(private_root)  # outside Git, 0700, NOFOLLOW
        ratefd,new=_open_locked_state(dirfd)
        started=_now(now)
        old=_read_state(ratefd,dirfd,new)
        if old is not None:
            previous,limit=old
            if started<previous:
                _refuse("LOCAL_RATE_CLOCK_MOVED_BACKWARDS")
            if started<limit:
                _refuse("SHARED_LEAGUE_RATE_WINDOW")
        _write_state(ratefd,dirfd,started,COOLDOWN_FAILURE,"RESERVED_OR_FAILED")
        attempted=1
        response=capture_once(match_id,private_root,getter=getter,now=now)
        if response["status"]!="RESEARCH_ONLY":
            return {**_report("ONE_SHOT_FAILED_LONG_COOLDOWN",attempted=1),
                    "shared_host_league_pacing_applied":True}
        _write_state(ratefd,dirfd,started,COOLDOWN_SUCCESS,"RESEARCH_ONLY")
        return {**_report("ONE_SHOT_CAPTURED_SINGLE_SOURCE_UNVERIFIED",attempted=1),
                "status":"RESEARCH_ONLY",
                "shared_host_league_pacing_applied":True,
                "original_response_readback_verified":
                    response["local_original_response_bytes_readback_verified"],
                "source_raw_sha256_unattested":
                    response["source_raw_sha256_unattested"],
                "archive_sha256_unattested":
                    response["archive_sha256_unattested"]}
    except PacingError as exc:
        return _report(str(exc),attempted=attempted)
    except Exception:
        return _report("UNSAFE_OR_UNAVAILABLE_SHARED_RATE_GATE",attempted=attempted)
    finally:
        if ratefd is not None:
            os.close(ratefd)
        if dirfd is not None:
            os.close(dirfd)
