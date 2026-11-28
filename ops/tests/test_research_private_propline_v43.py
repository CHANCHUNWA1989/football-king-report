import json
import unittest
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from ops.research_private_propline_v43 import private_components
NOW=datetime(2026,11,28,12,tzinfo=timezone.utc)
def fixture():
    book=lambda key: {"key":key,"markets":[{"key":"h2h","last_update":(NOW-timedelta(minutes=2)).isoformat(),
        "outcomes":[{"name":n,"price_decimal":p} for n,p in (("Arsenal",2.4),("Draw",3.3),("Chelsea",2.9))]}]}
    return {"id":"fixture1","sport_key":"soccer_epl","home_team":"Arsenal","away_team":"Chelsea",
        "commence_time":(NOW+timedelta(hours=2)).isoformat(),"bookmakers":[book("pinnacle"),book("bovada")]}
def run(rows,now=NOW):
    return private_components(json.dumps({"events":rows}).encode(),league="epl",
                               captured_utc=NOW.isoformat(),as_of=now.isoformat())
class PrivatePropLineTests(unittest.TestCase):
    def test_normalized_private_only(self):
        c,r=run([fixture()])
        self.assertEqual(len(c),1)
        self.assertAlmostEqual(sum(c[0]["market"]["p"]),1)
        self.assertFalse(r["publication_allowed"])
        self.assertNotIn("Arsenal",json.dumps(r))
        self.assertNotIn("pinnacle",json.dumps(c))
        self.assertEqual(r["authenticated_samples"],0)
    def test_duplicate_book_all_copies_excluded(self):
        d=fixture();d["bookmakers"].append(deepcopy(d["bookmakers"][0]))
        self.assertEqual(run([d])[0],[])
    def test_duplicate_fixture_all_copies_excluded(self):
        d=fixture();e=deepcopy(d);e["id"]="other"
        self.assertEqual(run([d,e])[0],[])
    def test_stale_and_future_quote_rejected(self):
        for offset in (-21,1):
            d=fixture();d["bookmakers"][0]["markets"][0]["last_update"]=(NOW+timedelta(minutes=offset)).isoformat()
            self.assertEqual(run([d])[0],[])
    def test_disagreeing_side_rejected(self):
        d=fixture();d["bookmakers"][0]["markets"][0]["outcomes"][0]["side"]="away"
        self.assertEqual(run([d])[0],[])
    def test_non_allowlisted_book_rejected(self):
        d=fixture();d["bookmakers"][1]["key"]="caesars"
        self.assertEqual(run([d])[0],[])
    def test_stale_capture_rejected(self):
        with self.assertRaises(ValueError):run([fixture()],NOW+timedelta(minutes=21))
