import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from research.kpl_v24_trial_activation_gate import audit_trial_activation_files

R = Path(__file__).resolve().parents[2] / "research"
F = R / "kpl_v23_20261104_ttg_wolves_fixture.json"
V = R / "kpl_v24_20261104_ttg_wolves_readiness.json"

class InputLinkTests(unittest.TestCase):
    def test_real_files_remain_hold(self):
        self.assertEqual(audit_trial_activation_files(F, V)["status"], "HOLD")

    def test_linked_evidence_is_blocked(self):
        with TemporaryDirectory() as tmp:
            link = Path(tmp) / "readiness.json"
            link.symlink_to(V)
            result = audit_trial_activation_files(F, link)
            self.assertEqual(result["reasons"], ["INVALID_OR_UNREADABLE_READINESS_FILES"])
