"""Constrained SSH forced-command stdio -> local private Unix broker adapter.

NO SSH SERVER IS CONFIGURED HERE. This Python file is ONLY a narrow
one-command protocol adapter for an operator-installed, independently
reviewed sshd forced-command account.

SSH authentication, host-key pinning, authorized_keys "restrict,command",
password disabling, filesystem access, remote egress firewall and identity
binding are enforced by OS / OpenSSH configuration, NOT Python environment
variables. SSH_CONNECTION is a spoofable structure hint, not proof.
Never expose a TCP listener; never forward SSH ports or agents for this task.

One JSON line in stdin, exactly one safe JSON line to stdout. No shell,
arbitrary URL, raw evidence, provider token, fixture names or API keys.
No actual provider HTTP from this bridge; dispatch uses PR555's local AF_UNIX
broker, which alone serializes PR543/PR546 requests under PR542 rate locks.

CI uses synthetic fake broker callback and NEVER starts sshd / real API GET.
"""
import ipaddress
import io
import json
import os
import select
import time
from collections.abc import Mapping
from pathlib import Path
import re
import sys

from inplay_openligadb_central_broker import (
    _hold as broker_hold,
    _parse_request,
    _private_root,
    request_private_broker,
    MAX_REQUEST,
    SCHEMA as BROKER_SCHEMA,
)

BRIDGE_SCHEMA="football-king-openligadb-ssh-stdio-bridge-v1"
MAX_STDIN_BYTES=MAX_REQUEST+1
READ_DEADLINE_SECONDS=3.0
SHA256=re.compile(r"[0-9a-f]{64}\Z")
NO_SESSION_KEYS=frozenset((
    "CI","GITHUB_ACTIONS","GITHUB_RUN_ID","RUNNER_OS",
    "ACTIONS_RUNTIME_TOKEN","GITHUB_TOKEN",
    "SSH_TTY","SSH_AUTH_SOCK","DISPLAY","XAUTHORITY",
    "LD_PRELOAD","LD_LIBRARY_PATH","PYTHONPATH","PYTHONINSPECT",
    "BASH_ENV","ENV",
))
RESPONSE_KEYS=frozenset(broker_hold().keys())


def _hold(reason="FORCED_SSH_BRIDGE_HOLD"):
    return {
        "schema":BRIDGE_SCHEMA,
        "status":"HOLD",
        "reason":reason,
        "ssh_session_structure_checked":False,
        "sshd_forced_command_policy_verified":False,
        "ssh_authentication_independently_verified":False,
        "ssh_host_key_pinned_and_verified":False,
        "cross_host_firewall_verified":False,
        "centralized_across_hosts_verified":False,
        "central_private_broker_used":False,
        "request_count":0,
        "change_status":None,
        "source_token_sha256_unattested":None,
        "archive_sha256_unattested":None,
        "local_raw_response_readback_verified":False,
        "source_authenticated":False,
        "externally_witnessed":False,
        "eligible_for_model_input":False,
        "eligible_for_model_scoring":False,
        "positive_ev_verified":False,
        "certified_forward_samples":0,
        "production_recommendations":"DISABLED",
        "recommendation":None,
        "roi":None,
    }


def _ssh_connection_valid(value):
    if type(value) is not str or len(value)>180:
        return False
    components=value.split()
    if len(components)!=4:
        return False
    try:
        ipaddress.ip_address(components[0])
        ipaddress.ip_address(components[2])
        for port in (components[1],components[3]):
            if not port.isascii() or not port.isdigit() or not 1<=int(port)<=65535:
                return False
    except (ValueError,TypeError):
        return False
    return True


def inspect_ssh_forced_context(environ=None):
    """Structural check only; cannot authenticate sshd from environment."""
    env=os.environ if environ is None else environ
    if not isinstance(env,Mapping) or any(
        type(k) is not str or type(v) is not str for k,v in env.items()
    ):
        return _hold("INVALID_SSH_PROCESS_ENVIRONMENT")
    names={key.upper() for key in env.keys()}
    if names & NO_SESSION_KEYS:
        return _hold("UNSAFE_SSH_SESSION_ENVIRONMENT")
    if "SSH_ORIGINAL_COMMAND" in env and env["SSH_ORIGINAL_COMMAND"]!="":
        return _hold("SSH_ORIGINAL_COMMAND_FORBIDDEN")
    if not _ssh_connection_valid(env.get("SSH_CONNECTION")):
        return _hold("SSH_FORCED_SESSION_NOT_PRESENT")
    if os.name!="posix" or not hasattr(os,"geteuid"):
        return _hold("UNSUPPORTED_SSH_RELAY_PLATFORM")
    try:
        if os.geteuid()==0:
            return _hold("PRIVILEGED_SSH_RELAY_FORBIDDEN")
    except (TypeError,OSError):
        return _hold("UNSUPPORTED_SSH_RELAY_PLATFORM")
    return {
        **_hold("UNATTESTED_SSH_ENVIRONMENT_STRUCTURE_ONLY"),
        "status":"RESEARCH_ONLY",
        "ssh_session_structure_checked":True,
    }


def _safe_upstream_reply(reply):
    """Never echo arbitrary broker fields, errors, URL, raw match or tokens."""
    if type(reply) is not dict or set(reply)!=RESPONSE_KEYS:
        return _hold("BROKER_RESPONSE_NOT_TRUSTED")
    if (
        reply.get("schema")!=BROKER_SCHEMA
        or reply.get("production_recommendations")!="DISABLED"
        or reply.get("eligible_for_model_input") is not False
        or reply.get("eligible_for_model_scoring") is not False
        or reply.get("source_authenticated") is not False
        or reply.get("cross_host_firewall_verified") is not False
        or reply.get("centralized_across_hosts_verified") is not False
        or reply.get("positive_ev_verified") is not False
        or reply.get("certified_forward_samples")!=0
        or reply.get("recommendation") is not None
        or reply.get("roi") is not None
        or reply.get("status") not in ("HOLD","RESEARCH_ONLY")
    ):
        return _hold("BROKER_RESPONSE_NOT_TRUSTED")
    if reply["status"]=="HOLD":
        return _hold("BROKER_RESEARCH_HOLD")
    if reply.get("central_private_broker_used") is not True:
        return _hold("BROKER_RESPONSE_NOT_TRUSTED")
    count=reply.get("request_count")
    if type(count) is not int or count not in (0,1):
        return _hold("BROKER_RESPONSE_NOT_TRUSTED")
    state=reply.get("change_status")
    if state not in (None,"BASELINE_ONLY","UNCHANGED","CHANGED_UNATTESTED"):
        return _hold("BROKER_RESPONSE_NOT_TRUSTED")
    token=reply.get("source_token_sha256_unattested")
    archive=reply.get("archive_sha256_unattested")
    for value in (token,archive):
        if value is not None and (
            type(value) is not str or SHA256.fullmatch(value) is None
        ):
            return _hold("BROKER_RESPONSE_NOT_TRUSTED")
    if type(reply.get("local_raw_response_readback_verified")) is not bool:
        return _hold("BROKER_RESPONSE_NOT_TRUSTED")
    return {
        **_hold("CENTRAL_BROKER_RESEARCH_ONLY_NO_REMOTE_ATTESTATION"),
        "status":"RESEARCH_ONLY",
        "ssh_session_structure_checked":True,
        "central_private_broker_used":True,
        "request_count":count,
        "change_status":state,
        "source_token_sha256_unattested":token,
        "archive_sha256_unattested":archive,
        "local_raw_response_readback_verified":
            reply["local_raw_response_readback_verified"],
    }


def _single_line_or_none(data):
    """Return only exactly one LF-terminated, bounded command."""
    if (type(data) is not bytes or not 1<=len(data)<=MAX_STDIN_BYTES
            or not data.endswith(b"\n") or data.count(b"\n")!=1):
        return None
    return data


def _read_one_command(reader, *, timeout_seconds=READ_DEADLINE_SECONDS):
    """Wait for ONE bounded JSON command *and EOF* with an absolute deadline.

    Unlike buffered .read(N), select+os.read on a real SSH stdin fd will NOT
    wait forever for an OpenSSH client that sends a line but keeps stdin open.
    Enforcing EOF is deliberate: otherwise an attacker could append a second
    command after the first one was dispatched. Buffered in-memory sources are
    allowed solely for deterministic no-network unit tests.
    """
    if (type(timeout_seconds) not in (int,float) or
            not 0<timeout_seconds<=30):
        return None
    if isinstance(reader,io.BytesIO):
        return _single_line_or_none(reader.read(MAX_STDIN_BYTES+1))
    try:
        fd=reader.fileno()
        if type(fd) is not int or fd<0:
            return None
        deadline=time.monotonic()+timeout_seconds
        data=bytearray()
        while True:
            remaining=deadline-time.monotonic()
            if remaining<=0:
                return None
            ready,_,_=select.select([fd],[],[],remaining)
            if not ready:
                return None
            # At most one extra byte beyond our permitted input length, so
            # even a continually writing client cannot consume unbounded RAM.
            chunk=os.read(fd,min(4096,MAX_STDIN_BYTES+1-len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data)>MAX_STDIN_BYTES or data.count(10)>1:
                return None
        return _single_line_or_none(bytes(data))
    except (OSError,ValueError,TypeError,AttributeError,OverflowError):
        return None


def relay_stdio_once(private_root,reader,writer,*,environ=None,
                     broker_request=None):
    """One EOF-terminated JSON command; always emit one sanitized JSON line.

    A remote client must close stdin after one line, e.g. pipe one JSON line
    over an authenticated SSH session. The bridge does NOT run a shell or
    execute SSH_ORIGINAL_COMMAND, and never returns raw provider responses.
    """
    check=inspect_ssh_forced_context(environ)
    if check["status"]!="RESEARCH_ONLY":
        result=_hold(check["reason"])
    else:
        try:
            root=_private_root(private_root)
            raw=_read_one_command(reader)
            if raw is None:
                result=_hold("INVALID_SSH_STDIO_COMMAND")
            else:
                try:
                    command=_parse_request(raw[:-1])
                except Exception:
                    result=_hold("INVALID_SSH_STDIO_COMMAND")
                else:
                    backend=request_private_broker if broker_request is None else broker_request
                    result=_safe_upstream_reply(backend(root,command))
        except Exception:
            result=_hold("SSH_STDIO_BRIDGE_OR_BROKER_UNAVAILABLE")
    try:
        writer.write(json.dumps(result,sort_keys=True,separators=(",",":"),
                                ensure_ascii=False,allow_nan=False).encode()+b"\n")
        writer.flush()
    except (OSError,ValueError,AttributeError):
        pass
    return result


def main(argv=None):
    """Entry only for independently configured OpenSSH forced command."""
    import argparse
    p=argparse.ArgumentParser(description="Forced SSH one-shot to private broker; NO TCP")
    p.add_argument("--private-root",required=True)
    p.add_argument("--forced-ssh-stdio",action="store_true",required=True)
    opts=p.parse_args(argv)
    output=relay_stdio_once(opts.private_root,sys.stdin.buffer,sys.stdout.buffer)
    raise SystemExit(0 if output["status"]=="RESEARCH_ONLY" else 2)


if __name__=="__main__":
    main()
