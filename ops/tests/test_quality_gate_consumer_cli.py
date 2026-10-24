"""Exercise the actual inventory/dashboard entrypoints without inherited PYTHONPATH."""
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class QualityConsumerCliTests(unittest.TestCase):
    def test_script_and_package_entrypoints_ignore_forged_gate_totals(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stamp = datetime.now(timezone.utc).isoformat()
            payloads = {
                "market": {"as_of_utc": stamp},
                "summary": {"captured_utc": stamp, "evidence_progress": {}},
                "gates": {"captured_utc": stamp, "passed": 7, "total": 7, "checks": []},
            }
            for name, payload in payloads.items():
                (root / (name + ".json")).write_text(json.dumps(payload), encoding="utf-8")
            for module in ("evidence_readiness_inventory", "build_zh_hant_dashboard"):
                for package_mode in (False, True):
                    with self.subTest(module=module, package_mode=package_mode):
                        output = root / (module + str(package_mode))
                        args = (["-m", "ops." + module] if package_mode else
                                [str(ROOT / "ops" / (module + ".py"))])
                        args += ["--summary", str(root / "summary.json"),
                                 "--gates", str(root / "gates.json"), "--output", str(output)]
                        if module == "evidence_readiness_inventory":
                            args += ["--market", str(root / "market.json")]
                        result = subprocess.run(
                            [sys.executable, *args], cwd=ROOT if package_mode else root,
                            env={"PYTHONPATH": "", "PYTHONDONTWRITEBYTECODE": "1"},
                            capture_output=True, text=True, timeout=15)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        if module == "evidence_readiness_inventory":
                            report = json.loads(output.read_text(encoding="utf-8"))
                            self.assertEqual(report["quality_gates_passed"], 0)
                            self.assertEqual(report["quality_gates_total"], 7)
                            self.assertIn("QUALITY_GATES_INCOMPLETE", report["blockers"])
                            self.assertEqual(report["production_recommendations"], "DISABLED")
                        else:
                            page = output.read_text(encoding="utf-8")
                            self.assertIn("0/7", page)
                            self.assertIn("out_of_sample_calibration", page)
                            self.assertIn("正式推薦：未開放", page)
