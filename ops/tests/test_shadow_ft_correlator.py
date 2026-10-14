import unittest
from shadow_ft_correlator import correlate
def bundle(score_a=[2,1],score_b=[2,1]):
    return {"sources":[
        {"provider":"OpenLigaDB","records":[{"home":"Bayern Munich","away":"Borussia Dortmund","kickoff_utc":"2026-10-12T12:00:00Z","score_ft":score_a}]},
        {"provider":"OpenFootball","records":[{"home":"Bayern Munich","away":"Borussia Dortmund","date":"2026-10-12","score_ft":score_b}]}]}
class CorrelationTests(unittest.TestCase):
    def test_agreement_not_certified(self):
        r=correlate(bundle())
        self.assertEqual(len(r["agreements"]),1)
        self.assertFalse(r["independently_verified"])
    def test_unmatched_first_is_not_ambiguous(self):
        b=bundle()
        b["sources"][1]["records"]=[]
        r=correlate(b)
        self.assertEqual(r["unmatched"],1)
        self.assertEqual(r["ambiguous"],0)
        self.assertEqual(r["unmatched_second"],0)
    def test_unmatched_second_is_counted(self):
        b=bundle()
        b["sources"][0]["records"]=[]
        r=correlate(b)
        self.assertEqual(r["unmatched_second"],1)
        self.assertEqual(r["unmatched"],0)
    def test_score_conflict(self):
        r=correlate(bundle([2,1],[0,1]))
        self.assertEqual(r["status"],"CONFLICT")
    def test_ambiguous_duplicate(self):
        b=bundle()
        b["sources"][0]["records"].append(dict(b["sources"][0]["records"][0]))
        self.assertEqual(correlate(b)["agreements"],[])
if __name__=="__main__":unittest.main()
