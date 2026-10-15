import unittest
from live_source_freshness import audit_snapshots

def row(source,score,updated="2026-10-15T10:33:00Z",fixture="A"):
    return {"source":source,"fixture_id":fixture,"observed_at":"2026-10-15T10:34:00Z",
            "updated_at":updated,"home_score":0,"away_score":score}

class FreshnessTests(unittest.TestCase):
    def test_newer_timestamp_wins(self):
        result=audit_snapshots([row("old",0,"2026-10-15T10:18:00Z"),row("new",1)],fixture_id="A")
        self.assertEqual(result["latest"]["source"],"new")
    def test_missing_timestamp_is_not_live(self):
        x=row("unknown",1)
        x.pop("updated_at")
        self.assertEqual(audit_snapshots([x],fixture_id="A")["status"],"UNVERIFIED")
    def test_mismatch_rejected(self):
        self.assertEqual(audit_snapshots([row("wrong",1,fixture="B")],fixture_id="A")["status"],"UNVERIFIED")
    def test_same_time_conflicting_scores(self):
        self.assertEqual(audit_snapshots([row("one",0),row("two",1)],fixture_id="A")["status"],"CONFLICT")
    def test_naive_time_rejected(self):
        self.assertEqual(audit_snapshots([row("x",1,"2026-10-15T10:33:00")],fixture_id="A")["status"],"UNVERIFIED")

if __name__=="__main__":
    unittest.main()
