"""Ensure cached GitHub main metadata cannot attest a later website readback."""
from pathlib import Path
import unittest

PAGE = Path(__file__).resolve().parents[2] / "docs/control-tower-mobile/index.html"

class MobileReadbackAgeTests(unittest.TestCase):
    def test_main_metadata_expires_before_site_sha_comparison(self):
        source = PAGE.read_text(encoding="utf-8")
        self.assertIn("Date.now()-Date.parse(S.main.checked_at_utc)>=0", source)
        self.assertIn("Date.now()-Date.parse(S.main.checked_at_utc)<=600000", source)
        self.assertIn("S.site={status:'HOLD'", source)
        self.assertIn("release_authorized:false", source)

if __name__ == "__main__":
    unittest.main()
