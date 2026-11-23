"""Read-only SSH host policy auditor for Football King research.

This inspects a *local snapshot* of sshd -T -C effective Match policy and
the dedicated account's one-key authorized_keys. It never configures sshd,
writes authorized_keys, reads private keys, opens listening sockets or
touches the existing central OpenLigaDB broker. It cannot prove that the
running daemon uses the inspected config, that the remote host has a pinned
host key, that authentication occurred, or that OS/firewall egress is denied.

Successful structural checks are RESEARCH_ONLY, NEVER a deployment pass.
"""
import base64
import binascii
import ipaddress
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess

SCHEMA="football-king-openligadb-sshd-policy-snapshot-audit-v1"
EXPECTED_SSHD_BINARY="/usr/sbin/sshd"
MAX_EFFECTIVE_BYTES=262144
MAX_KEYS_BYTES=65536
MAX_KEY_ROWS=1

REQUIRED_EFFECTIVE={
    "authenticationmethods":"publickey",
    "passwordauthentication":"no",
    "kbdinteractiveauthentication":"no",
    "pubkeyauthentication":"yes",
    "permitrootlogin":"no",
    "disableforwarding":"yes",
    "allowtcpforwarding":"no",
    "allowstreamlocalforwarding":"no",
    "allowagentforwarding":"no",
    "x11forwarding":"no",
    "permittty":"no",
    "permituserrc":"no",
    "permituserenvironment":"no",
    "hostbasedauthentication":"no",
    "gssapiauthentication":"no",
    "kerberosauthentication":"no",
    "permitemptypasswords":"no",
    "authorizedkeyscommand":"none",
    "trustedusercakeys":"none",
    "maxsessions":"1",
}
SAFE_PATH=re.compile(r"/[A-Za-z0-9_./-]+\Z")
PYTHON_BIN=re.compile(r"/usr/(?:local/)?bin/python3(?:\.[0-9]{1,2})?\Z")
USER=re.compile(r"[a-z_][a-z0-9_-]{0,31}\Z")
PUBKEY=re.compile(r"([A-Za-z0-9+/]+={0,2})\Z")
COMMENT=re.compile(r"[a-zA-Z0-9_.@+-]{1,80}\Z")


def _report(reason="POLICY_NOT_VERIFIED"):
    return {
        "schema":SCHEMA,
        "status":"HOLD",
        "reason":reason,
        "actual_local_host_snapshot_read":False,
        "effective_sshd_snapshot_constraints_passed":False,
        "authorized_keys_snapshot_constraints_passed":False,
        "authorized_keys_file_owner_and_mode_checked":False,
        "sshd_running_process_policy_verified":False,
        "ssh_authentication_independently_verified":False,
        "client_host_key_pinning_verified":False,
        "sshd_forced_command_actually_enforced_verified":False,
        "host_firewall_egress_verified":False,
        "cross_host_firewall_verified":False,
        "centralized_across_hosts_verified":False,
        "ready_for_actual_provider_http":False,
        "source_authenticated":False,
        "eligible_for_model_input":False,
        "positive_ev_verified":False,
        "certified_forward_samples":0,
        "production_recommendations":"DISABLED",
        "recommendation":None,
        "roi":None,
    }


def _abs_safe_path(value):
    return (type(value) is str and len(value)<=240
            and SAFE_PATH.fullmatch(value) is not None
            and "//" not in value
            and all(part not in (".","..") for part in value.split("/")[1:])
            and value!="/")


def validate_forced_command(command):
    """Only a fixed Python bridge invocation. No shell punctuation/options."""
    if type(command) is not str or len(command)>700 or "\t" in command:
        return False
    parts=command.split(" ")
    if len(parts)!=5 or not all(parts):
        return False
    python_bin,script,flag,private_root,mode=parts
    return (
        PYTHON_BIN.fullmatch(python_bin) is not None
        and _abs_safe_path(script)
        and script.endswith("/ops/inplay_openligadb_ssh_stdio_bridge.py")
        and flag=="--private-root"
        and _abs_safe_path(private_root)
        and private_root!=script
        and mode=="--forced-ssh-stdio"
    )


def _effective_structural_ok(text,expected):
    if (type(text) is not str or not text or len(text.encode("utf-8"))>MAX_EFFECTIVE_BYTES
            or "\r" in text or "\x00" in text):
        return False
    parsed={}
    for line in text.splitlines():
        if not line or line.startswith("#") or " " not in line or "\t" in line:
            return False
        key,val=line.split(" ",1)
        if not key.isascii() or not re.fullmatch(r"[a-z][a-z0-9]*",key):
            return False
        if key in parsed and (key in REQUIRED_EFFECTIVE or key=="forcecommand"):
            # Duplicate security-critical effective directives are ambiguous.
            return False
        # Non-security multivalue directives (for example AcceptEnv) may
        # appear on multiple lines; they must not conceal required directives.
        parsed[key]=val
    return (
        parsed.get("forcecommand")==expected
        and all(parsed.get(key)==value for key,value in REQUIRED_EFFECTIVE.items())
    )


def _valid_ed25519_blob(b64):
    if PUBKEY.fullmatch(b64) is None or len(b64)>600:
        return False
    try:
        body=base64.b64decode(b64,validate=True)
    except (binascii.Error,ValueError):
        return False
    # SSH public blob: string algorithm name, then string 32-byte public key.
    magic=b"ssh-ed25519"
    return (
        len(body)==4+len(magic)+4+32
        and body[:4]==len(magic).to_bytes(4,"big")
        and body[4:4+len(magic)]==magic
        and body[4+len(magic):8+len(magic)]==(32).to_bytes(4,"big")
    )


def _keys_structural_ok(text,expected):
    if (type(text) is not str or not text or
            len(text.encode("utf-8"))>MAX_KEYS_BYTES
            or "\r" in text or "\x00" in text):
        return False
    lines=[ln.strip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if len(lines)!=MAX_KEY_ROWS:
        return False
    # This intentionally accepts ONLY a dedicated exact-form public key:
    # restrict,command="EXACT" ssh-ed25519 BASE64 [OPTIONAL_COMMENT]
    # Never accept more key options (pty, agent-forwarding, permitopen, etc.)
    line=lines[0]
    prefix='restrict,command="'+expected+'" ssh-ed25519 '
    if not line.startswith(prefix):
        return False
    fields=line[len(prefix):].split(" ")
    if len(fields) not in (1,2):
        return False
    if len(fields)==2 and COMMENT.fullmatch(fields[1]) is None:
        return False
    return _valid_ed25519_blob(fields[0])


def analyze_policy_snapshots(effective_sshd,authorized_keys,expected_command):
    """Analyze untrusted text without treating it as live enforcement evidence."""
    result=_report("SSHD_OR_KEY_RESTRICTIONS_NOT_CONFIRMED")
    if not validate_forced_command(expected_command):
        return {**result,"reason":"UNSAFE_EXPECTED_BRIDGE_COMMAND"}
    try:
        sshd_ok=_effective_structural_ok(effective_sshd,expected_command)
        keys_ok=_keys_structural_ok(authorized_keys,expected_command)
    except (ValueError,TypeError,UnicodeError,OverflowError):
        return result
    result={
        **result,
        "effective_sshd_snapshot_constraints_passed":sshd_ok,
        "authorized_keys_snapshot_constraints_passed":keys_ok,
    }
    if sshd_ok and keys_ok:
        return {
            **result,
            "status":"RESEARCH_ONLY",
            "reason":"SNAPSHOT_RESTRICTIONS_MATCH_NOT_LIVE_ATTESTED",
        }
    return result


def _safe_read_public_authorized_keys(username,key_path):
    """Dedicated 0700 .ssh dir and 0600 regular public-key file only.

    Avoid logging any public key material or path. No reading private keys.
    Checks inode/owner after NOFOLLOW open and caps total bytes.
    """
    if (type(username) is not str or USER.fullmatch(username) is None
            or username=="root" or type(key_path) is not str):
        raise ValueError("INVALID_HOST_INSPECTION_SCOPE")
    user=pwd.getpwnam(username)
    home=Path(user.pw_dir)
    directory=home/".ssh"
    expected=directory/"authorized_keys"
    if (not _abs_safe_path(str(expected)) or key_path!=str(expected)
            or not directory.is_dir() or directory.is_symlink()):
        raise ValueError("INVALID_PUBLIC_KEY_PATH")
    parent=directory.lstat()
    if (parent.st_uid!=user.pw_uid or not stat.S_ISDIR(parent.st_mode)
            or stat.S_IMODE(parent.st_mode)!=0o700):
        raise ValueError("UNSAFE_PUBLIC_KEY_DIRECTORY")
    pre=expected.lstat()
    if (not stat.S_ISREG(pre.st_mode) or pre.st_uid!=user.pw_uid
            or pre.st_nlink!=1 or stat.S_IMODE(pre.st_mode)!=0o600
            or not 0<pre.st_size<=MAX_KEYS_BYTES):
        raise ValueError("UNSAFE_PUBLIC_KEY_FILE")
    descriptor=os.open(expected,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW)
    try:
        opened=os.fstat(descriptor)
        after=expected.lstat()
        if (opened.st_dev,opened.st_ino)!=(pre.st_dev,pre.st_ino) or (
            opened.st_dev,opened.st_ino)!=(after.st_dev,after.st_ino):
            raise ValueError("PUBLIC_KEY_FILE_RACED")
        if (opened.st_size!=pre.st_size or opened.st_uid!=user.pw_uid
                or opened.st_nlink!=1 or
                stat.S_IMODE(opened.st_mode)!=0o600):
            raise ValueError("UNSAFE_PUBLIC_KEY_FILE")
        data=os.read(descriptor,MAX_KEYS_BYTES+1)
        post=os.fstat(descriptor)
        if (len(data)!=opened.st_size or len(data)>MAX_KEYS_BYTES or
                post.st_size!=opened.st_size or
                post.st_mtime_ns!=opened.st_mtime_ns):
            raise ValueError("PUBLIC_KEY_FILE_CHANGED")
        return data.decode("utf-8")
    finally:
        os.close(descriptor)


def inspect_local_host(username,client_ip,server_ip,server_port,
                       authorized_keys_path,expected_command):
    """Read-only snapshot on host; does NOT change or attest running sshd.

    Must run manually ON the intended host with access to /usr/sbin/sshd and
    the dedicated user's public authorized_keys. It never reads SSH private
    keys. Existing processes, firewall policy, sshd reload, remote endpoint
    identity and bypassable other authentication files remain unverified.
    """
    base=_report("ACTUAL_HOST_SNAPSHOT_UNAVAILABLE")
    try:
        if (type(username) is not str or USER.fullmatch(username) is None
                or username=="root" or type(server_port) is not int
                or not 1<=server_port<=65535
                or not validate_forced_command(expected_command)):
            return base
        client=ipaddress.ip_address(client_ip)
        server=ipaddress.ip_address(server_ip)
        if not isinstance(client_ip,str) or not isinstance(server_ip,str):
            return base
        # Keep this invocation for exactly the supplied user/address.
        # sshd(8) -T -C is read-only effective config for a connection spec.
        context=("user="+username+",host="+str(client)+",addr="+str(client)
                 +",laddr="+str(server)+",lport="+str(server_port))
        key_text=_safe_read_public_authorized_keys(
            username,authorized_keys_path)
        result=subprocess.run(
            [EXPECTED_SSHD_BINARY,"-T","-C",context],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,timeout=5,check=False,
            env={"PATH":"/usr/sbin:/usr/bin"},
        )
        if result.returncode!=0 or type(result.stdout) is not str:
            return base
        audit=analyze_policy_snapshots(result.stdout,key_text,expected_command)
        # This indicates a local process inspected snapshots, not that
        # sshd's *currently running* process uses this configuration.
        return {**audit,
                "actual_local_host_snapshot_read":True,
                "authorized_keys_file_owner_and_mode_checked":True}
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,
            subprocess.SubprocessError,OverflowError):
        return base


def main(argv=None):
    """No network request or privilege changes; emits only safe booleans."""
    import argparse
    import json
    parser=argparse.ArgumentParser(description="Read-only sshd -T and public key policy preflight")
    parser.add_argument("--user",required=True)
    parser.add_argument("--client-ip",required=True)
    parser.add_argument("--server-ip",required=True)
    parser.add_argument("--server-port",type=int,required=True)
    parser.add_argument("--authorized-keys",required=True)
    parser.add_argument("--expected-command",required=True)
    parser.add_argument("--manual-read-only",action="store_true",required=True)
    args=parser.parse_args(argv)
    result=inspect_local_host(args.user,args.client_ip,args.server_ip,
                              args.server_port,args.authorized_keys,
                              args.expected_command)
    print(json.dumps(result,ensure_ascii=False,sort_keys=True,allow_nan=False))
    # A structurally good snapshot is a research-only success; never a
    # deployment permission or betting system promotion.
    raise SystemExit(0 if result["status"]=="RESEARCH_ONLY" else 2)


if __name__=="__main__":
    main()
