import hashlib
import sys
import unittest
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from screenshot_evidence_intake import intake
NOW=datetime(2026,10,9,14,tzinfo=timezone.utc)
IMAGE=b"test-image-content"
def manifest():
    return {"image_sha256":hashlib.sha256(IMAGE).hexdigest(),
            "fixture":{"event_id":"e1","league":"soccer_epl",
                       "home":"Home","away":"Away"},
            "screenshot":{"event_id":"e1","human_reviewed":True,
                          "observed_at_utc":"2026-10-09T13:59:30Z",
                          "home_goals":1,"away_goals":0,"minute":75.5}}

class ScreenshotEvidenceTests(unittest.TestCase):
    def test_reviewed_manifest_is_research_only_not_ocr(self):
        r=intake(IMAGE,manifest(),now=NOW)
        self.assertEqual(r["status"],"RESEARCH_ONLY")
        self.assertFalse(r["ocr_performed"])
        self.assertFalse(r["fixture_independently_verified"])
        self.assertEqual(r["case"]["fixture"]["independent_fixture_sources"],0)

    def test_hash_mismatch_holds(self):
        m=manifest()
        m["image_sha256"]="wrong"
        self.assertIn("IMAGE_HASH_MISMATCH",intake(IMAGE,m,now=NOW)["blockers"])

    def test_old_screenshot_holds(self):
        m=manifest()
        m["screenshot"]["observed_at_utc"]="2026-10-09T13:50:00Z"
        self.assertIn("SCREENSHOT_STALE_OR_FUTURE",intake(IMAGE,m,now=NOW)["blockers"])

    def test_cross_match_id_holds(self):
        m=manifest()
        m["screenshot"]["event_id"]="different"
        self.assertIn("SCREENSHOT_EVENT_MISMATCH",intake(IMAGE,m,now=NOW)["blockers"])

    def test_unreviewed_manifest_holds(self):
        m=manifest()
        m["screenshot"]["human_reviewed"]=False
        self.assertIn("SCREENSHOT_NOT_HUMAN_REVIEWED",intake(IMAGE,m,now=NOW)["blockers"])

    def test_boolean_score_rejected(self):
        m=manifest()
        m["screenshot"]["home_goals"]=True
        self.assertIn("INVALID_HOME_GOALS",intake(IMAGE,m,now=NOW)["blockers"])

    def test_nan_minute_rejected(self):
        m=manifest()
        m["screenshot"]["minute"]=float("nan")
        self.assertIn("INVALID_MATCH_MINUTE",intake(IMAGE,m,now=NOW)["blockers"])

    def test_fake_ocr_confidence_rejected(self):
        m=manifest()
        m["screenshot"]["ocr_confidence"]=0.99
        self.assertIn("UNVERIFIED_OCR_CONFIDENCE",intake(IMAGE,m,now=NOW)["blockers"])

    def test_duplicate_teams_rejected(self):
        m=manifest()
        m["fixture"]["away"]="home"
        self.assertIn("DUPLICATE_TEAMS",intake(IMAGE,m,now=NOW)["blockers"])

    def test_empty_image_rejected(self):
        with self.assertRaises(ValueError):
            intake(b"",manifest(),now=NOW)

    def test_invalid_manifest_rejected(self):
        with self.assertRaises(ValueError):
            intake(IMAGE,[],now=NOW)

    def test_untrusted_independent_source_claim_removed(self):
        m=manifest()
        m["fixture"]["independent_fixture_sources"]=100
        r=intake(IMAGE,m,now=NOW)
        self.assertEqual(r["case"]["fixture"]["independent_fixture_sources"],0)

if __name__=="__main__":
    unittest.main()
