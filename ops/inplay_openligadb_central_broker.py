"""Opt-in single-host Unix-domain central ingress for OpenLigaDB research.

One manually started server process accepts SMALL, typed, local-only commands
and calls the existing PR543 probe / PR546 changed-token capture using the
SAME dedicated 0700 private directory and PR542 league-wide flock/rate state.
The original provider response bytes stay in that central private directory;
a client receives only fixed non-sensitive statuses and unattested hashes.

This is NOT a remote TCP listener and does NOT establish cross-host egress
firewall enforcement. Authorized remote hosts would require separately
reviewed SSH/Unix-socket forwarding and OS outbound-deny controls; none are
configured or certified here. CI uses fake getter callbacks, never a
provider API request. No service is started automatically or in GitHub Actions.
"""
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import stat
import struct

from ops.shadow_raw_source_collector import strict_json_loads
from inplay_private_local_store import _root_fd
from inplay_openligadb_manual_egress import (
    require_manual_egress, ManualEgressDenied,
)
from inplay_openligadb_lastchange_probe import (
    probe_once, _probe_url,
)
from inplay_openligadb_conditional_capture import conditional_capture_once
from inplay_openligadb_one_shot import _endpoint

SCHEMA="football-king-openligadb-private-broker-v1"
REQUEST_SCHEMA="football-king-openligadb-broker-command-v1"
BROKER_SOCKET=".openligadb-bl1-research-broker.sock"
MAX_REQUEST=512
MAX_REPLY=2048
HEX64=re.compile(r"[0-9a-f]{64}\Z")


class BrokerError(ValueError):
    """Fixed error code with no paths, env values, input bodies or secrets."""


def _hold(reason="BROKER_REQUEST_HOLD"):
    return {
        "schema":SCHEMA,
        "status":"HOLD",
        "reason":reason,
        "request_count":0,
        "central_private_broker_used":False,
        "centralized_across_hosts_verified":False,
        "cross_host_firewall_verified":False,
        "socket_authentication_is_cross_host_mtls":False,
        "change_status":None,
        "local_raw_response_readback_verified":False,
        "archive_sha256_unattested":None,
        "source_token_sha256_unattested":None,
        "source_authenticated":False,
        "provider_time_authenticated":False,
        "eligible_for_model_input":False,
        "eligible_for_model_scoring":False,
        "positive_ev_verified":False,
        "certified_forward_samples":0,
        "production_recommendations":"DISABLED",
        "recommendation":None,
        "roi":None,
    }


def _parse_request(payload):
    if type(payload) is not bytes or not 1<=len(payload)<=MAX_REQUEST:
        raise BrokerError("INVALID_BROKER_COMMAND")
    try:
        value=strict_json_loads(payload)
    except (TypeError,ValueError,UnicodeError,RecursionError,OverflowError):
        raise BrokerError("INVALID_BROKER_COMMAND") from None
    if type(value) is not dict or value.get("schema")!=REQUEST_SCHEMA:
        raise BrokerError("INVALID_BROKER_COMMAND")
    action=value.get("action")
    expected={"schema","action","season","group"}
    if action=="capture":
        expected.add("match_id")
    elif action!="probe":
        raise BrokerError("INVALID_BROKER_COMMAND")
    if set(value)!=expected:
        raise BrokerError("INVALID_BROKER_COMMAND")
    try:
        _probe_url(value["season"],value["group"])
        if action=="capture":
            _endpoint(value["match_id"])
    except (ValueError,KeyError,TypeError):
        raise BrokerError("INVALID_BROKER_COMMAND") from None
    return value


def _public_response(out,action):
    # Never copy potentially tainted provider JSON, URL, fixture name,
    # HTTP receipt, path, raw token or free-form source exception to client.
    if not isinstance(out,dict):
        return _hold("UPSTREAM_RESEARCH_GATE_HOLD")
    ok=out.get("status")=="RESEARCH_ONLY"
    result={
        **_hold("UNATTESTED_LOCAL_PROBE" if ok and action=="probe" else
                "UNATTESTED_LOCAL_CAPTURE" if ok else "UPSTREAM_RESEARCH_GATE_HOLD"),
        "status":"RESEARCH_ONLY" if ok else "HOLD",
        "central_private_broker_used":True,
    }
    requested=out.get("requests_attempted",0)
    if type(requested) is int and requested in (0,1):
        result["request_count"]=requested
    if action=="probe" and ok:
        state=out.get("change_status")
        if state in ("BASELINE_ONLY","UNCHANGED","CHANGED_UNATTESTED"):
            result["change_status"]=state
        digest=out.get("source_token_sha256_unattested")
        if type(digest) is str and HEX64.fullmatch(digest):
            result["source_token_sha256_unattested"]=digest
    if action=="capture" and ok:
        result["local_raw_response_readback_verified"]=(
            out.get("local_original_response_bytes_readback_verified") is True)
        digest=out.get("archive_sha256_unattested")
        if type(digest) is str and HEX64.fullmatch(digest):
            result["archive_sha256_unattested"]=digest
        else:
            return _hold("UNUSABLE_PRIVATE_CAPTURE_DIGEST")
    return result


def _private_root(root):
    descriptor=None
    try:
        descriptor=_root_fd(root)
        value=Path(root)
        if not value.is_absolute():
            raise BrokerError("BROKER_PRIVATE_ROOT_REQUIRED")
        return value
    except (ValueError,TypeError,OSError,BrokerError):
        raise BrokerError("BROKER_PRIVATE_ROOT_UNSAFE") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _local_peer_same_user(sock):
    # Linux SO_PEERCRED is an additional check. Permission and private
    # directory verification remain mandatory on all supported POSIX hosts.
    if hasattr(socket,"SO_PEERCRED"):
        try:
            peer=sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,
                                 struct.calcsize("3i"))
            _,uid,_=struct.unpack("3i",peer)
            return uid==os.getuid()
        except (OSError,struct.error):
            return False
    if hasattr(sock,"getpeereid"):
        try:
            uid,_=sock.getpeereid()
            return uid==os.getuid()
        except OSError:
            return False
    return False  # no peer-identity check, no service.


class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(3)
        try:
            if not self.server.verify_endpoint():
                result=_hold("BROKER_ENDPOINT_NOT_PRIVATE")
            elif not _local_peer_same_user(self.request):
                result=_hold("BROKER_PEER_NOT_AUTHORIZED")
            else:
                line=self.rfile.readline(MAX_REQUEST+2)
                if not line.endswith(b"\n") or len(line)>MAX_REQUEST+1:
                    result=_hold("INVALID_BROKER_COMMAND")
                else:
                    try:
                        req=_parse_request(line[:-1])
                        if req["action"]=="probe":
                            out=probe_once(req["season"],req["group"],
                                           self.server.root,
                                           getter=self.server.probe_getter,
                                           now=self.server.clock)
                        else:
                            out=conditional_capture_once(
                                req["match_id"],req["season"],req["group"],
                                self.server.root,getter=self.server.match_getter,
                                now=self.server.clock)
                        result=_public_response(out,req["action"])
                    except BrokerError as exc:
                        result=_hold(str(exc))
        except Exception:
            result=_hold("BROKER_REQUEST_UNAVAILABLE")
        try:
            raw=json.dumps(result,sort_keys=True,separators=(",",":"),
                           ensure_ascii=False,allow_nan=False).encode()+b"\n"
            self.wfile.write(raw)
            self.wfile.flush()
        except (OSError,ValueError):
            pass


class _PrivateServer(socketserver.UnixStreamServer):
    allow_reuse_address=False
    request_queue_size=4

    def verify_endpoint(self):
        fd=None
        try:
            fd=_root_fd(self.root)
            current=os.stat(BROKER_SOCKET,dir_fd=fd,
                            follow_symlinks=False)
            return (
                stat.S_ISSOCK(current.st_mode)
                and current.st_uid==os.getuid()
                and stat.S_IMODE(current.st_mode)==0o600
                and (current.st_dev,current.st_ino)==self.socket_identity
            )
        except (OSError,ValueError,TypeError):
            return False
        finally:
            if fd is not None:
                os.close(fd)

    def server_close(self):
        # Do not unlink any path swapped by another local process.
        try:
            if self.verify_endpoint():
                os.unlink(self.server_address)
        except OSError:
            pass
        super().server_close()


def open_private_broker(private_root,*,probe_getter=None,
                        match_getter=None,now=None):
    """Create private Unix socket, but DO NOT call serve_forever.

    Real transport is disallowed on CI/hosted runners by the PR552 gate;
    tests must inject BOTH fake getters. External SSH / firewall setup and
    any cross-host deployment remain explicit external responsibilities.
    """
    if (probe_getter is None) != (match_getter is None):
        raise BrokerError("MIXED_REAL_AND_SYNTHETIC_TRANSPORT_FORBIDDEN")
    if probe_getter is None:
        try:
            require_manual_egress()
        except ManualEgressDenied:
            raise BrokerError("REAL_BROKER_ENVIRONMENT_NOT_APPROVED") from None
    root=_private_root(private_root)
    path=root/BROKER_SOCKET
    if os.path.lexists(path):
        raise BrokerError("BROKER_SOCKET_ALREADY_EXISTS")
    try:
        server=_PrivateServer(str(path),_Handler)
    except OSError:
        raise BrokerError("BROKER_SOCKET_NOT_AVAILABLE") from None
    try:
        os.chmod(path,0o600)
        st=os.lstat(path)
        server.root=root
        server.clock=now
        server.probe_getter=probe_getter
        server.match_getter=match_getter
        server.socket_identity=(st.st_dev,st.st_ino)
        if not server.verify_endpoint():
            raise BrokerError("BROKER_SOCKET_NOT_PRIVATE")
        return server
    except Exception:
        server.server_close()
        raise BrokerError("BROKER_SOCKET_NOT_AVAILABLE") from None



# Client-side defense in depth: an untrusted local socket peer could
# return extra JSON keys or conflicting attestation claims. Do not expose
# raw server JSON directly to the caller, even if sensitive flags look safe.
# The trusted local broker itself constructs fixed-size replies in _Handler.
REPLY_MUTABLE_FIELDS=frozenset((
    "status","reason","request_count","central_private_broker_used",
    "change_status","local_raw_response_readback_verified",
    "archive_sha256_unattested","source_token_sha256_unattested",
))
KNOWN_HOLD_REASONS=frozenset((
    "BROKER_REQUEST_HOLD","BROKER_ENDPOINT_NOT_PRIVATE",
    "BROKER_PEER_NOT_AUTHORIZED","INVALID_BROKER_COMMAND",
    "BROKER_REQUEST_UNAVAILABLE","UPSTREAM_RESEARCH_GATE_HOLD",
    "UNUSABLE_PRIVATE_CAPTURE_DIGEST",
))
KNOWN_CHANGE_STATES=frozenset(("BASELINE_ONLY","UNCHANGED",
                                "CHANGED_UNATTESTED"))


def _validated_broker_reply(parsed,action):
    """Only a fixed, benign response schema may cross the socket boundary.

    action must come from parsing the client's submitted command, never
    from the received reply. Every returned dict is newly synthesized; no
    arbitrary server string, raw HTTP data or optional field can escape.
    """
    invalid=_hold("BROKER_REPLY_INVALID")
    base=_hold()
    if type(parsed) is not dict or set(parsed)!=set(base):
        return invalid
    for key,expected in base.items():
        if key not in REPLY_MUTABLE_FIELDS:
            value=parsed[key]
            if type(value) is not type(expected) or value!=expected:
                return invalid

    status=parsed["status"]
    reason=parsed["reason"]
    count=parsed["request_count"]
    used=parsed["central_private_broker_used"]
    if (type(status) is not str or status not in ("HOLD","RESEARCH_ONLY")
            or type(reason) is not str
            or type(count) is not int or count not in (0,1)
            or type(used) is not bool
            or type(parsed["local_raw_response_readback_verified"]) is not bool):
        return invalid

    token=parsed["source_token_sha256_unattested"]
    archive=parsed["archive_sha256_unattested"]
    state=parsed["change_status"]
    for digest in (token,archive):
        if digest is not None and (
                type(digest) is not str or HEX64.fullmatch(digest) is None):
            return invalid

    if status=="HOLD":
        if (reason not in KNOWN_HOLD_REASONS or state is not None
                or token is not None or archive is not None
                or parsed["local_raw_response_readback_verified"] is not False):
            return invalid
        # Do not reproduce optional metadata from rejected requests,
        # only the vetted fixed reason code.
        return _hold(reason)

    if action not in ("probe","capture") or used is not True:
        return invalid
    if action=="probe":
        if (reason!="UNATTESTED_LOCAL_PROBE"
                or state not in KNOWN_CHANGE_STATES
                or type(token) is not str
                or archive is not None
                or parsed["local_raw_response_readback_verified"] is not False):
            return invalid
    else:
        if (reason!="UNATTESTED_LOCAL_CAPTURE"
                or state is not None or token is not None
                or type(archive) is not str
                or parsed["local_raw_response_readback_verified"] is not True):
            return invalid

    # Copy only prevalidated scalar values into a fresh fixed schema.
    return {
        **_hold(reason),
        "status":"RESEARCH_ONLY",
        "request_count":count,
        "central_private_broker_used":True,
        "change_status":state,
        "source_token_sha256_unattested":token,
        "archive_sha256_unattested":archive,
        "local_raw_response_readback_verified":
            parsed["local_raw_response_readback_verified"],
    }

def request_private_broker(private_root,command):
    """One local Unix socket request; no provider URL or secret arguments.

    Caller must already have OS permission to reach a socket in the 0700
    private root. This client makes no external network request itself.
    """
    try:
        root=_private_root(private_root)
        path=root/BROKER_SOCKET
        if type(command) is dict:
            data=json.dumps(command,sort_keys=True,separators=(",",":"),
                            ensure_ascii=False,allow_nan=False).encode()+b"\n"
        elif type(command) is bytes:
            data=command
        else:
            return _hold("INVALID_BROKER_COMMAND")
        # Send bounded malformed payloads to the server for fail-closed
        # evaluation; never attempt unbounded reads or echo the payload.
        if len(data)>MAX_REQUEST+2:
            data=b"X"*(MAX_REQUEST+1)+b"\n"
        # A broker cannot certify a RESEARCH_ONLY response for an invalid
        # command or a different action. Parse only our own outbound bytes.
        try:
            if not data.endswith(b"\n"):
                raise BrokerError("INVALID_BROKER_COMMAND")
            action=_parse_request(data[:-1])["action"]
        except (BrokerError,ValueError,TypeError):
            action=None
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            client.settimeout(4)
            client.connect(str(path))
            client.sendall(data)
            with client.makefile("rb") as stream:
                answer=stream.readline(MAX_REPLY+2)
        if not answer.endswith(b"\n") or len(answer)>MAX_REPLY+1:
            return _hold("BROKER_REPLY_INVALID")
        parsed=strict_json_loads(answer[:-1])
        return _validated_broker_reply(parsed,action)
    except Exception:
        return _hold("BROKER_ENDPOINT_NOT_PRIVATE")


def main(argv=None):
    """Manual, blocking, non-daemon opt-in. Never start on GitHub Actions."""
    import argparse
    parser=argparse.ArgumentParser(description="Private central OpenLigaDB research socket; no TCP")
    parser.add_argument("--private-root",required=True)
    parser.add_argument("--serve-manual-broker",action="store_true",required=True)
    args=parser.parse_args(argv)
    try:
        require_manual_egress()
        server=open_private_broker(args.private_root)
    except (ManualEgressDenied,BrokerError):
        print(json.dumps(_hold("REAL_BROKER_ENVIRONMENT_NOT_APPROVED"),
                         sort_keys=True))
        raise SystemExit(2)
    try:
        with server:
            server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    raise SystemExit(0)


if __name__=="__main__":
    main()
