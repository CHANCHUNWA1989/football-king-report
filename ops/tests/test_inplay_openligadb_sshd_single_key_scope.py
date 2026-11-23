"""Negative tests for OpenSSH alternate public key and certificate authority paths.

The prior PR563 parsed only the contents of ~/.ssh/authorized_keys.
sshd AuthorizedKeysFile can contain multiple paths. Thus a good-looking
checked key could coexist with an uninspected alternate key that allows SSH
access. These fake sshd -T snapshots must all fail closed without sshd calls.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from inplay_openligadb_sshd_policy_audit import analyze_policy_snapshots
from test_inplay_openligadb_sshd_policy_audit import (
    COMMAND, PUB, authorized, effective,
)


class OnlyOneSSHAuthorizedKeySourceTests(unittest.TestCase):
    def audit(self, text):
        return analyze_policy_snapshots(text,authorized(),COMMAND)

    def test_exactly_one_authorized_key_path_is_allowed_structurally(self):
        report=self.audit(effective(authorizedkeysfile=".ssh/authorized_keys"))
        self.assertEqual(report["status"],"RESEARCH_ONLY")
        self.assertTrue(report["effective_sshd_snapshot_constraints_passed"])
        self.assertTrue(report["authorized_keys_snapshot_constraints_passed"])
        self.assertFalse(report["sshd_running_process_policy_verified"])
        self.assertFalse(report["ssh_authentication_independently_verified"])
        self.assertFalse(report["host_firewall_egress_verified"])
        self.assertFalse(report["ready_for_actual_provider_http"])
        self.assertFalse(report["eligible_for_model_input"])
        self.assertEqual(report["certified_forward_samples"],0)
        self.assertEqual(report["production_recommendations"],"DISABLED")

    def test_default_second_authorized_keys2_path_refused(self):
        text=effective(authorizedkeysfile=".ssh/authorized_keys .ssh/authorized_keys2")
        self.assertEqual(self.audit(text)["status"],"HOLD")

    def test_additional_system_and_user_key_paths_refused(self):
        for value in (
            ".ssh/authorized_keys /etc/ssh/keys/%u",
            "%h/.ssh/authorized_keys /etc/ssh/emergency",
            ".ssh/authorized_keys2",
            "/tmp/other_authorized_keys",
            ".ssh/authorized_keys .ssh/authorized_keys",
            "none",
        ):
            with self.subTest(value=value):
                result=self.audit(effective(authorizedkeysfile=value))
                self.assertEqual(result["status"],"HOLD")

    def test_missing_authorizedkeysfile_never_assumes_safe_default(self):
        fields=[x for x in effective().splitlines()
                if not x.startswith("authorizedkeysfile ")]
        # Missing key path is an unverified policy, not an implicit default.
        self.assertEqual(self.audit("\n".join(fields)+"\n")["status"],"HOLD")

    def test_duplicate_authorizedkeysfile_is_rejected_even_if_same(self):
        for value in (".ssh/authorized_keys",".ssh/authorized_keys2"):
            with self.subTest(value=value):
                self.assertEqual(
                    self.audit(effective()+"authorizedkeysfile "+value+"\n")["status"],
                    "HOLD",
                )

    def test_authorized_principals_file_other_than_none_refused(self):
        for value in (".ssh/authorized_principals",
                      "/etc/ssh/principals/%u",
                      "%h/.ssh/principals"):
            with self.subTest(value=value):
                self.assertEqual(
                    self.audit(effective(authorizedprincipalsfile=value))["status"],
                    "HOLD")

    def test_authorized_principals_command_other_than_none_refused(self):
        for value in ("/usr/local/bin/lookup-principal",
                      "/bin/sh", "/usr/bin/python3 /tmp/query"):
            self.assertEqual(
                self.audit(effective(authorizedprincipalscommand=value))["status"],
                "HOLD")

    def test_missing_principal_policy_fields_fail_closed(self):
        for missing in ("authorizedprincipalsfile","authorizedprincipalscommand"):
            text="\n".join(x for x in effective().splitlines()
                           if not x.startswith(missing+" "))+"\n"
            with self.subTest(missing=missing):
                self.assertEqual(self.audit(text)["status"],"HOLD")

    def test_trusted_ca_and_key_lookup_command_still_refused(self):
        for param,value in (("trustedusercakeys","/etc/ssh/ca.pub"),
                            ("authorizedkeyscommand","/usr/local/bin/ldap-keys")):
            self.assertEqual(self.audit(effective(**{param:value}))["status"],"HOLD")

    def test_forced_command_cannot_mitigate_an_extra_key_file(self):
        # A restrictive effective ForceCommand might limit what a second
        # key can do; it does not prove identity/authorization of that key.
        other=effective(authorizedkeysfile=".ssh/authorized_keys /etc/ssh/breakglass")
        report=self.audit(other)
        self.assertEqual(report["status"],"HOLD")
        self.assertFalse(report["effective_sshd_snapshot_constraints_passed"])
        self.assertFalse(report["ready_for_actual_provider_http"])
        self.assertNotIn(PUB,str(report))
        self.assertNotIn(COMMAND,str(report))

    def test_case_and_extra_whitespace_cannot_bypass_exact_single_path(self):
        for value in (".ssh/Authorized_Keys",".ssh/authorized_keys ",
                      "./.ssh/authorized_keys",
                      "%h/.ssh/authorized_keys"):
            self.assertEqual(
                self.audit(effective(authorizedkeysfile=value))["status"],"HOLD")

    def test_structural_success_does_not_claim_actual_host_enforcement(self):
        report=self.audit(effective())
        self.assertEqual(report["status"],"RESEARCH_ONLY")
        for field in (
            "sshd_running_process_policy_verified",
            "ssh_authentication_independently_verified",
            "sshd_forced_command_actually_enforced_verified",
            "client_host_key_pinning_verified",
            "host_firewall_egress_verified",
            "cross_host_firewall_verified",
            "centralized_across_hosts_verified",
            "ready_for_actual_provider_http",
            "source_authenticated",
            "eligible_for_model_input",
            "positive_ev_verified",
        ):
            with self.subTest(field=field):
                self.assertFalse(report[field])


if __name__=="__main__":
    unittest.main()
