"""Guard against silent BSD archive success with literal variable target path."""
import unittest
from pathlib import Path

WORKFLOW=(Path(__file__).resolve().parents[2] /
          ".github/workflows/football-king-bsd-free.yml")

class BSDArchiveTargetTests(unittest.TestCase):
    def test_array_expands_to_distinct_archive_targets(self):
        source=WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('targets=("$history" "sources/bsd_status_latest.json")',source)
        self.assertIn('if [ "$eligible" = True ]; then targets+=("sources/bsd_market_latest.json"); fi',source)
        self.assertIn('for target in "${targets[@]}"; do',source)
        self.assertNotIn('for target in "\\${targets[@]}"; do',source)
        self.assertIn('if [[ "$target" == *.gz ]]; then',source)
        self.assertIn('payload="$(base64 -w0 bsd/bsd-result.json)"',source)

if __name__=="__main__":
    unittest.main()
