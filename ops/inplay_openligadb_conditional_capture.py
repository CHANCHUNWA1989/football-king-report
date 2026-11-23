"""Manual changed-token conditional OpenLigaDB single-match raw byte capture.

One reviewed, explicit operation, never automatic polling:
- Requires two previous lastchangedate observations for the *same* league,
  season, and group, with changed tokens persisted by PR543.
- Requires the same shared-host PR542 90s/600s league gate.
- Create-only durable *reservation* for the exact matchID/group/token before
  requesting match data. A failure/crash also permanently consumes this token.
- Verify native matchID+leagueSeason+groupOrderID inside the real response,
  and PR538 writes and replays the exact original HTTP response privately.

A changed matchday token is NOT proof that a selected match changed. The
provider token may change between the probe and full match GET. No signature,
independent timestamp, globally distributed gate, authorized bookmaker odds,
actual red cards, xG, calibration, betting or actual model input.
"""
import hashlib
import json
import os
import re
import stat
from datetime import timedelta

from inplay_private_local_store import _root_fd
from inplay_openligadb_one_shot import (
    _endpoint, _now, _validate_raw, _fetch_one as _fetch_match, capture_once,
)
from inplay_openligadb_lastchange_probe import (
    _probe_url, _read_checkpoint,
)
from inplay_openligadb_league_pacing import (
    _open_locked_state, _read_state, _write_state,
    COOLDOWN_SUCCESS, COOLDOWN_FAILURE,
)

SCHEMA="football-king-openligadb-changed-token-manual-capture-v1"
MAX_CHANGE_AGE=timedelta(minutes=5)
TOKEN_HASH=re.compile(r"[0-9a-f]{64}\Z")


class ConditionalFailure(ValueError):
    """Fixed public-safe reason only; never exception text from HTTP."""


def _reject(reason):
    raise ConditionalFailure(reason)


def _report(reason="CONDITIONAL_GET_NOT_ADMITTED",attempted=0):
    return {
        "schema":SCHEMA,
        "status":"HOLD",
        "reason":reason,
        "requests_attempted":attempted,
        "same_host_change_probe_required":True,
        "centralized_across_hosts":False,
        "token_consumption_reservation_persisted":False,
        "shared_host_league_pacing_applied":False,
        "local_original_response_bytes_readback_verified":False,
        "archive_sha256_unattested":None,
        "source_raw_sha256_unattested":None,
        "source_authenticated":False,
        "provider_issued_time_authenticated":False,
        "token_to_match_body_causality_proven":False,
        "source_independence_verified":False,
        "externally_witnessed":False,
        "eligible_for_model_input":False,
        "eligible_for_model_scoring":False,
        "actual_live_score_verified":False,
        "red_cards_available":False,
        "odds_or_xg_verified":False,
        "positive_ev_verified":False,
        "certified_forward_samples":0,
        "production_recommendations":"DISABLED",
        "recommendation":None,
        "roi":None,
    }


def _reservation_name(season,group,match_id,token_sha):
    _probe_url(season,group)
    _endpoint(match_id)
    if type(token_sha) is not str or TOKEN_HASH.fullmatch(token_sha) is None:
        _reject("INVALID_CHANGE_TOKEN_DIGEST")
    return (".openligadb-bl1-reserve-s"+str(season)+"-g"+str(group)+
            "-m"+str(match_id)+"-"+token_sha+".json")


def _reserve_create_only(dirfd,name,season,group,match_id,token_sha,clock):
    # Called while the shared PR542 flock is held. We deliberately do not
    # modify/delete a reservation after the HTTP attempt.
    entry={
        "schema":SCHEMA,"season":season,"group_order_id":group,
        "match_id":match_id,"token_sha256":token_sha,
        "reserved_utc_unattested":clock.isoformat(),
        "state":"RESERVED_OR_CAPTURED",
        "production_recommendations":"DISABLED",
    }
    data=json.dumps(entry,sort_keys=True,separators=(",",":"),
                    allow_nan=False).encode("utf-8")
    fd=None
    try:
        fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
                   os.O_NOFOLLOW|os.O_NONBLOCK,0o600,dir_fd=dirfd)
        info=os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1
                or stat.S_IMODE(info.st_mode)!=0o600
                or info.st_uid!=os.getuid()):
            _reject("UNSAFE_TOKEN_RESERVATION")
        with os.fdopen(fd,"wb") as stream:
            fd=None
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(dirfd)
        from ops.private_response_capture import _read
        check=_read(dirfd,name,4096)
        if check!=data:
            _reject("TOKEN_RESERVATION_READBACK_FAILED")
    except FileExistsError:
        _reject("TOKEN_ALREADY_RESERVED_OR_CAPTURED")
    except ConditionalFailure:
        raise
    except (OSError,ValueError,TypeError):
        _reject("TOKEN_RESERVATION_NOT_SAFE")
    finally:
        if fd is not None:
            os.close(fd)


def conditional_capture_once(match_id,season,group,private_root,*,getter=None,now=None):
    """Manual full match GET only after a recent *unattested* changed marker.

    Each specific token can be consumed once per native matchID, even if
    the actual full request fails. No actual API request is made by tests.
    """
    dirfd=lockfd=None
    attempted=0
    reserved=False
    try:
        expected_url=_endpoint(match_id)
        _probe_url(season,group)
        dirfd=_root_fd(private_root)
        lockfd,new=_open_locked_state(dirfd)
        current=_now(now)
        previous=_read_state(lockfd,dirfd,new)
        check=_read_checkpoint(dirfd,season,group)
        if check is None or check["transition"]!="CHANGED_UNATTESTED":
            _reject("CHANGE_NOT_DEMONSTRATED")
        observed_at=__import__("inplay_openligadb_one_shot")._utc(check["observed_utc"])
        age=current-observed_at
        if age<timedelta(0):
            _reject("LOCAL_CHANGE_CLOCK_MOVED_BACKWARDS")
        # A previous failure consumes the token even if the checkpoint is
        # now stale or the long failure cooldown has elapsed.
        digest=check["token_sha256"]
        name=_reservation_name(season,group,match_id,digest)
        try:
            os.stat(name,dir_fd=dirfd,follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            _reject("TOKEN_ALREADY_RESERVED_OR_CAPTURED")
        if age>MAX_CHANGE_AGE:
            _reject("CHANGE_CHECKPOINT_TOO_OLD")
        if previous is not None:
            last,not_before=previous
            if current<last:
                _reject("LOCAL_RATE_CLOCK_MOVED_BACKWARDS")
            if current<not_before:
                _reject("SHARED_LEAGUE_RATE_WINDOW")
        _reserve_create_only(dirfd,name,season,group,match_id,digest,current)
        reserved=True
        # Do not extend a successful initial reservation window on failure;
        # unfinished and crashed attempts retain the 600s embargo.
        _write_state(lockfd,dirfd,current,COOLDOWN_FAILURE,"RESERVED_OR_FAILED")
        attempted=1

        def checked_fetch(url):
            if url!=expected_url:
                _reject("UNEXPECTED_NATIVE_MATCH_ENDPOINT")
            request=_fetch_match if getter is None else getter
            payload=request(url)  # single GET, at most once
            if type(payload) is not tuple or len(payload)!=4:
                _reject("MALFORMED_NATIVE_MATCH_RESPONSE")
            raw,status,media,final=payload
            if (type(status) is not int or status!=200
                    or type(final) is not str or final!=url
                    or type(media) is not str):
                _reject("MALFORMED_NATIVE_MATCH_RESPONSE")
            item=_validate_raw(raw,match_id,_now(now))
            native_group=item.get("group")
            if (type(item.get("leagueSeason")) is not int
                    or item["leagueSeason"]!=season
                    or type(native_group) is not dict
                    or type(native_group.get("groupOrderID")) is not int
                    or native_group["groupOrderID"]!=group):
                _reject("NATIVE_MATCH_GROUP_OR_SEASON_MISMATCH")
            return payload

        recorded=capture_once(match_id,private_root,getter=checked_fetch,now=now)
        if recorded["status"]!="RESEARCH_ONLY":
            return {**_report("MATCH_RESPONSE_REJECTED_TOKEN_CONSUMED",attempted=1),
                    "token_consumption_reservation_persisted":True,
                    "shared_host_league_pacing_applied":True}
        _write_state(lockfd,dirfd,current,COOLDOWN_SUCCESS,"RESEARCH_ONLY")
        return {**_report("UNATTESTED_CHANGED_GROUP_TOKEN_CAPTURED",attempted=1),
                "status":"RESEARCH_ONLY",
                "token_consumption_reservation_persisted":True,
                "shared_host_league_pacing_applied":True,
                "local_original_response_bytes_readback_verified":
                    recorded["local_original_response_bytes_readback_verified"],
                "archive_sha256_unattested":recorded["archive_sha256_unattested"],
                "source_raw_sha256_unattested":recorded["source_raw_sha256_unattested"]}
    except ConditionalFailure as exc:
        return {**_report(str(exc),attempted=attempted),
                "token_consumption_reservation_persisted":reserved}
    except Exception:
        return {**_report("CONDITIONAL_CAPTURE_HOLD_UNTRUSTED_OR_UNAVAILABLE",attempted=attempted),
                "token_consumption_reservation_persisted":reserved}
    finally:
        if lockfd is not None:
            os.close(lockfd)
        if dirfd is not None:
            os.close(dirfd)


def main(argv=None):
    import argparse
    p=argparse.ArgumentParser(description="Manual OpenLigaDB changed-token match capture, research only")
    p.add_argument("--match-id",type=int,required=True)
    p.add_argument("--season",type=int,required=True)
    p.add_argument("--group-order",type=int,required=True)
    p.add_argument("--private-root",required=True)
    p.add_argument("--manual-changed-only",required=True,action="store_true")
    a=p.parse_args(argv)
    output=conditional_capture_once(a.match_id,a.season,a.group_order,a.private_root)
    print(json.dumps(output,sort_keys=True,ensure_ascii=False,allow_nan=False))
    raise SystemExit(0 if output["status"]=="RESEARCH_ONLY" else 2)


if __name__=="__main__":
    main()
