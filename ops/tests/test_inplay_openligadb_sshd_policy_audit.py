"""Read-only sshd effective-policy audit: synthetic snapshots, no sshd or API."""
import base64
import os
from pathlib import Path
import stat
import tempfile
import types
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from inplay_openligadb_sshd_policy_audit import (
    analyze_policy_snapshots, inspect_local_host, validate_forced_command,
    EXPECTED_SSHD_BINARY,
)

COMMAND=("/usr/bin/python3 /opt/football-king/ops/inplay_openligadb_ssh_stdio_bridge.py"
         " --private-root /srv/football-king-private --forced-ssh-stdio")
BLOB=(len(b"ssh-ed25519")).to_bytes(4,"big")+b"ssh-ed25519"+(32).to_bytes(4,"big")+bytes(range(32))
PUB=base64.b64encode(BLOB).decode()


def authorized(command=COMMAND):
    return 'restrict,command="'+command+'" ssh-ed25519 '+PUB+' test@client\n'


def effective(**patches):
    data={
        "forcecommand":COMMAND,
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
        "authorizedkeysfile":".ssh/authorized_keys",
        "authorizedprincipalsfile":"none",
        "authorizedprincipalscommand":"none",
        "trustedusercakeys":"none",
        "maxsessions":"1",
    }
    data.update(patches)
    return "".join(k+" "+v+"\n" for k,v in data.items())


class SSHDPolicySnapshotAuditTests(unittest.TestCase):
    def test_strict_policy_and_exact_restricted_key_is_structural_research_only(self):
        r=analyze_policy_snapshots(effective(),authorized(),COMMAND)
        self.assertEqual(r["status"],"RESEARCH_ONLY")
        self.assertTrue(r["effective_sshd_snapshot_constraints_passed"])
        self.assertTrue(r["authorized_keys_snapshot_constraints_passed"])
        self.assertFalse(r["sshd_running_process_policy_verified"])
        self.assertFalse(r["ssh_authentication_independently_verified"])
        self.assertFalse(r["host_firewall_egress_verified"])
        self.assertFalse(r["cross_host_firewall_verified"])
        self.assertFalse(r["client_host_key_pinning_verified"])
        self.assertFalse(r["ready_for_actual_provider_http"])
        self.assertFalse(r["eligible_for_model_input"])
        self.assertFalse(r["positive_ev_verified"])
        self.assertEqual(r["certified_forward_samples"],0)
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertIsNone(r["recommendation"])
        self.assertIsNone(r["roi"])
        self.assertNotIn(PUB,str(r))
        self.assertNotIn("test@client",str(r))

    def test_missing_effective_sshd_snapshot_is_hold(self):
        for text in ("", "forcecommand "+COMMAND+"\n",None):
            self.assertEqual(analyze_policy_snapshots(text,authorized(),COMMAND)["status"],"HOLD")

    def test_authentication_fallback_is_never_accepted(self):
        for name,value in (
            ("passwordauthentication","yes"),
            ("kbdinteractiveauthentication","yes"),
            ("authenticationmethods","any"),
            ("authenticationmethods","publickey,password"),
            ("pubkeyauthentication","no"),
            ("hostbasedauthentication","yes"),
            ("gssapiauthentication","yes"),
        ):
            with self.subTest(name=name):
                r=analyze_policy_snapshots(effective(**{name:value}),authorized(),COMMAND)
                self.assertEqual(r["status"],"HOLD")

    def test_shell_forwarding_and_pty_are_all_rejected(self):
        for name,value in (
            ("forcecommand","none"),("forcecommand","/bin/sh"),
            ("disableforwarding","no"),("allowtcpforwarding","yes"),
            ("allowstreamlocalforwarding","yes"),
            ("allowagentforwarding","yes"),("x11forwarding","yes"),
            ("permittty","yes"),("permituserrc","yes"),
            ("permituserenvironment","yes"),("permitrootlogin","yes"),
        ):
            with self.subTest(name=name):
                r=analyze_policy_snapshots(effective(**{name:value}),authorized(),COMMAND)
                self.assertEqual(r["status"],"HOLD")

    def test_unknown_external_auth_and_overrides_rejected(self):
        for name,value in (
            ("authorizedkeyscommand","/tmp/untrusted"),
            ("trustedusercakeys","/tmp/ca"),
            ("maxsessions","10"),
            ("kerberosauthentication","yes"),
            ("permitemptypasswords","yes"),
        ):
            with self.subTest(name=name):
                self.assertEqual(analyze_policy_snapshots(
                    effective(**{name:value}),authorized(),COMMAND)["status"],"HOLD")

    def test_duplicate_effective_key_conflict_fails(self):
        data=effective()+"passwordauthentication yes\n"
        self.assertEqual(analyze_policy_snapshots(data,authorized(),COMMAND)["status"],"HOLD")

    def test_public_key_without_forced_command_rejected(self):
        self.assertEqual(analyze_policy_snapshots(
            effective(),"ssh-ed25519 "+PUB+"\n",COMMAND)["status"],"HOLD")

    def test_restrict_with_pty_or_agent_reenable_rejected(self):
        for extra in ("pty","agent-forwarding","port-forwarding","X11-forwarding","permitopen=\"any\""):
            line=authorized().replace("restrict,command=", "restrict,"+extra+",command=")
            self.assertEqual(analyze_policy_snapshots(effective(),line,COMMAND)["status"],"HOLD")

    def test_different_or_multiple_forced_commands_rejected(self):
        others=(
            authorized(COMMAND+" --other"),
            authorized(COMMAND)+"ssh-ed25519 "+PUB+"\n",
            authorized(COMMAND)+authorized(COMMAND).replace("test@client","different"),
        )
        for text in others:
            self.assertEqual(analyze_policy_snapshots(effective(),text,COMMAND)["status"],"HOLD")

    def test_malformed_key_base64_or_cert_ca_rejected(self):
        cases=[
            authorized().replace(PUB,"SECRET!"),
            authorized().replace("ssh-ed25519 ","cert-authority ssh-ed25519 "),
            authorized().replace("ssh-ed25519 ","ssh-rsa "),
            authorized().replace("restrict,",""),
        ]
        for value in cases:
            self.assertEqual(analyze_policy_snapshots(effective(),value,COMMAND)["status"],"HOLD")

    def test_command_rejects_shell_metacharacters_relative_script_or_bad_private_path(self):
        cases=[
            COMMAND+"; id", COMMAND.replace("/usr/bin/python3","python3"),
            COMMAND.replace("/opt/football-king/ops","../ops"),
            COMMAND.replace("/srv/football-king-private","~/private"),
            COMMAND.replace("--forced-ssh-stdio","--manual-one-shot"),
            COMMAND.replace("/usr/bin/python3","/bin/sh"),
        ]
        for cmd in cases:
            self.assertFalse(validate_forced_command(cmd))
            self.assertEqual(analyze_policy_snapshots(effective(),authorized(),cmd)["status"],"HOLD")
        self.assertTrue(validate_forced_command(COMMAND))

    def test_oversize_and_nontext_snapshots_fail_closed(self):
        cases=[
            ("A"*300000,authorized()),
            (effective(),"X"*300000),
            (effective().encode(),authorized()),
            (effective(),authorized().encode()),
            (effective().replace("\n","\r\n"),authorized()),
        ]
        for a,b in cases:
            self.assertEqual(analyze_policy_snapshots(a,b,COMMAND)["status"],"HOLD")

    def test_error_never_contains_key_material_command_path_or_ssh_text(self):
        bad=authorized().replace("restrict,","")
        r=analyze_policy_snapshots(effective(),bad,COMMAND)
        self.assertNotIn(PUB,str(r))
        self.assertNotIn(COMMAND,str(r))
        self.assertNotIn("test@client",str(r))

    def test_read_only_host_missing_file_fails_without_spawn(self):
        with patch("inplay_openligadb_sshd_policy_audit.subprocess.run",
                   side_effect=AssertionError("MUST_NOT_SPAWN")) as runner:
            r=inspect_local_host("researchsvc","192.0.2.10","192.0.2.20",22,
                                 "/path/not/exist",COMMAND)
        self.assertEqual(r["status"],"HOLD")
        runner.assert_not_called()
        self.assertFalse(r["actual_local_host_snapshot_read"])

    def test_host_rejects_root_wildcard_user_and_injection_addresses(self):
        for user,client,server,port in (
            ("root","192.0.2.10","192.0.2.20",22),
            ("*", "192.0.2.10","192.0.2.20",22),
            ("researchsvc","1.2.3.4,addr=evil","192.0.2.20",22),
            ("researchsvc","192.0.2.10","192.0.2.20",True),
            ("researchsvc","192.0.2.10","192.0.2.20",65536),
        ):
            with self.subTest(user=user,client=client,port=port):
                r=inspect_local_host(user,client,server,port,"/not/present",COMMAND)
                self.assertEqual(r["status"],"HOLD")

    def test_positive_read_only_runner_is_not_deployment_attestation(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)
            (base/".ssh").mkdir(mode=0o700)
            key_path=base/".ssh"/"authorized_keys"
            key_path.write_text(authorized(),encoding="utf-8")
            key_path.chmod(0o600)
            st=key_path.stat()
            fake_pwd=types.SimpleNamespace(pw_uid=st.st_uid,pw_dir=str(base))
            seen=[]
            def runner(argv,**kwargs):
                seen.append((argv,kwargs))
                return types.SimpleNamespace(returncode=0,stdout=effective(),stderr="")
            with patch("inplay_openligadb_sshd_policy_audit.pwd.getpwnam",return_value=fake_pwd):
                with patch("inplay_openligadb_sshd_policy_audit.subprocess.run",side_effect=runner):
                    r=inspect_local_host("researchsvc","192.0.2.10",
                                         "192.0.2.20",22,str(key_path),COMMAND)
            self.assertEqual(r["status"],"RESEARCH_ONLY")
            self.assertTrue(r["actual_local_host_snapshot_read"])
            self.assertTrue(r["effective_sshd_snapshot_constraints_passed"])
            self.assertFalse(r["ssh_authentication_independently_verified"])
            self.assertFalse(r["sshd_running_process_policy_verified"])
            self.assertFalse(r["host_firewall_egress_verified"])
            self.assertEqual(seen[0][0][0],EXPECTED_SSHD_BINARY)
            self.assertEqual(seen[0][0][1:3],["-T","-C"])
            self.assertNotIn(PUB,str(r))
            self.assertNotIn(str(key_path),str(r))

    def test_symlink_public_key_file_and_wrong_mode_fail_before_sshd(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            ssh=root/".ssh"
            ssh.mkdir(mode=0o700)
            file=ssh/"authorized_keys"
            file.write_text(authorized())
            file.chmod(0o644)
            fake_pwd=types.SimpleNamespace(pw_uid=os.getuid(),pw_dir=str(root))
            with patch("inplay_openligadb_sshd_policy_audit.pwd.getpwnam",return_value=fake_pwd):
                with patch("inplay_openligadb_sshd_policy_audit.subprocess.run",
                           side_effect=AssertionError("NO_SPAWN")) as run:
                    r=inspect_local_host("researchsvc","192.0.2.10","192.0.2.20",
                                         22,str(file),COMMAND)
                    self.assertEqual(r["status"],"HOLD")
                    file.chmod(0o600)
                    file.unlink()
                    file.symlink_to(root/"target")
                    self.assertEqual(inspect_local_host(
                        "researchsvc","192.0.2.10","192.0.2.20",22,str(file),COMMAND)["status"],"HOLD")
                    run.assert_not_called()

if __name__=="__main__":
    unittest.main()
