import unittest
from cross_source_ft_diagnostic import reconcile

def row(provider,home="A",away="B",score=None):
    x={"provider":provider,"status":"FT","home":home,"away":away,"score_ft":score or [2,1]}
    if provider=="OpenLigaDB":x["kickoff_utc"]="2026-10-10T14:00:00Z"
    else:x["match_date"]="2026-10-10"
    return x

class CrossSourceTests(unittest.TestCase):
    def test_exact_agreement_still_not_verified(self):
        r=reconcile([row("OpenLigaDB"," A ","B")],[row("OpenFootball","a","b")])
        self.assertEqual(r["exact_agreement_count"],1)
        self.assertFalse(r["independently_verified"])
        self.assertFalse(r["external_provenance_rechecked"])
        self.assertEqual(r["production_recommendations"],"DISABLED")
    def test_disagreement_and_duplicate_rejected(self):
        a=row("OpenLigaDB")
        b=row("OpenFootball",score=[0,0])
        self.assertEqual(reconcile([a],[b])["disagreement_count"],1)
        self.assertEqual(reconcile([a,a],[b])["ambiguous_match_keys"],1)
        self.assertEqual(reconcile([a,a],[b])["exact_agreement_count"],0)
    def test_name_mismatch_no_guess(self):
        self.assertEqual(reconcile([row("OpenLigaDB","FC A")],[row("OpenFootball","A")])["exact_agreement_count"],0)
    def test_wrong_date_no_guess(self):
        b=row("OpenFootball");b["match_date"]="2026-10-11"
        self.assertEqual(reconcile([row("OpenLigaDB")],[b])["exact_agreement_count"],0)
if __name__=="__main__":
    unittest.main()
