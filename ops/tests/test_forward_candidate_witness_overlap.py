import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from forward_candidate_witness_overlap import join, evidence_rows, research_score

def rows():
    c={"league":"bundesliga","home":"SV Werder Bremen","away":"Borussia Mönchengladbach","kickoff_utc_recorded":"2026-11-27T19:30:00+00:00","openligadb_match_id":83253,"thesportsdb_event_id":"2508822"}
    r={**c,"home":"Werder Bremen","event_id":"openligadb:83253","source_prediction_utc":"2026-11-25T10:00:00+00:00","candidate_generated_utc":"2026-11-25T10:15:00+00:00","verified_tlog_utc":"2026-11-25T10:24:21+00:00","observed_before_recorded_kickoff":True}
    return c,r
class WitnessOverlapTests(unittest.TestCase):
    def state(self,c,r):
        d=join([c],r)
        self.assertEqual(d["verified_forward_sample_credit"],0)
        self.assertFalse(d["rows"][0]["source_identity_authenticated"])
        return d["rows"][0]["state"]
    def test_native(self):
        c,r=rows();self.assertEqual(self.state(c,[r]),"EXACT_NATIVE_ID_WITNESS_CANDIDATE")
    def test_team_time_only(self):
        c,r=rows();r["event_id"]="other:83253"
        self.assertEqual(self.state(c,[r]),"TEAM_TIME_WITNESS_ONLY")
    def test_wrong_native(self):
        c,r=rows();r["event_id"]="openligadb:83254"
        self.assertEqual(self.state(c,[r]),"NATIVE_ID_FIXTURE_CONFLICT")
    def test_duplicate(self):
        c,r=rows();self.assertEqual(self.state(c,[r,r]),"AMBIGUOUS_FORECAST")
    def test_missing(self):
        c,r=rows();self.assertEqual(self.state(c,[]),"NO_WITNESSED_FORECAST_MATCH")
    def test_clock(self):
        c,r=rows();r["verified_tlog_utc"]="2026-11-27T19:25:00+00:00"
        self.assertEqual(self.state(c,[r]),"WITNESS_CLOCK_REJECTED")
    def test_native_other_fixture(self):
        c,r=rows();r["kickoff_utc_recorded"]="2026-11-27T19:31:00+00:00"
        self.assertEqual(self.state(c,[r]),"NATIVE_ID_FIXTURE_CONFLICT")

    def evidence(self):
        c,r=rows()
        r.update(original=[.5,.3,.2],derived_rho0=[.5,.3,.2],candidate=[.48,.34,.18],
                 source_projection_sha256="a"*64,model_id="fixed-test",protocol_sha256="b"*64)
        f={"candidates":[c]};l=join([c],[r]);p={"rows":[{**c,"state":"AWAITING_RECORDED_KICKOFF_PLUS_2H","observed_scores":None}]}
        return f,l,[r],p
    def test_evidence_preserves_vectors_and_pending(self):
        f,l,r,p=self.evidence();d=evidence_rows(f,l,r,p)
        self.assertEqual(d["signed_native_id_count"],1)
        self.assertEqual(d["rows"][0]["signed_probabilities_1x2"]["candidate"],r[0]["candidate"])
        self.assertIsNone(d["rows"][0]["observed_scores"])
        self.assertEqual(d["verified_forward_sample_credit"],0)
    def test_evidence_refuses_missing_or_duplicate(self):
        f,l,r,p=self.evidence()
        with self.assertRaisesRegex(ValueError,"EVIDENCE_COHORT_MISMATCH"):evidence_rows(f,l,r,{"rows":[]})
        with self.assertRaisesRegex(ValueError,"DUPLICATE_EVIDENCE_ID"):evidence_rows(f,l,r,{"rows":p["rows"]*2})
        with self.assertRaisesRegex(ValueError,"SIGNED_ROW_CONFLICT"):evidence_rows(f,l,[],p)
    def test_evidence_no_backfill(self):
        f,l,r,p=self.evidence();l["rows"][0]["state"]="TEAM_TIME_WITNESS_ONLY"
        d=evidence_rows(f,l,r,p)
        self.assertIsNone(d["rows"][0]["signed_probabilities_1x2"])
        self.assertEqual(d["signed_native_id_count"],0)
    def test_evidence_bad_probability(self):
        f,l,r,p=self.evidence();r[0]["candidate"]=[.8,.8,.8]
        with self.assertRaisesRegex(ValueError,"INVALID_SIGNED_PROBABILITIES"):evidence_rows(f,l,r,p)

    def test_score_pending_no_metrics(self):
        d=research_score(evidence_rows(*self.evidence()))
        self.assertEqual(d["observed_agreement_n"],0)
        self.assertIsNone(d["metrics"])
    def test_score_same_fixture(self):
        f,l,r,p=self.evidence()
        p["rows"][0].update(state="TWO_PUBLISHER_SCORE_AGREEMENT_UNVERIFIED",observed_scores=[[1,0],[1,0]])
        d=research_score(evidence_rows(f,l,r,p))
        self.assertEqual(d["observed_agreement_n"],1)
        self.assertEqual(d["verified_forward_sample_credit"],0)
        for v in d["metrics"].values():self.assertEqual(v["n"],1);self.assertEqual(v["correct"],1)
        self.assertAlmostEqual(d["metrics"]["original"]["brier"],.38)
        self.assertAlmostEqual(d["metrics"]["original"]["log_loss"],.6931471805599453)
    def test_score_conflict_and_duplicate(self):
        f,l,r,p=self.evidence()
        p["rows"][0].update(state="TWO_PUBLISHER_SCORE_AGREEMENT_UNVERIFIED",observed_scores=[[1,0],[0,1]])
        with self.assertRaisesRegex(ValueError,"SCORE_AGREEMENT_CONFLICT"):research_score(evidence_rows(f,l,r,p))
        d=evidence_rows(*self.evidence());d["rows"]*=2
        with self.assertRaisesRegex(ValueError,"DUPLICATE_SCORE_ID"):research_score(d)
    def test_score_excludes_unwitnessed_and_conflicting(self):
        f,l,r,p=self.evidence();l["rows"][0]["state"]="TEAM_TIME_WITNESS_ONLY"
        self.assertEqual(research_score(evidence_rows(f,l,r,p))["excluded"],{"NO_EXACT_WITNESS":1})
        f,l,r,p=self.evidence();p["rows"][0]["state"]="SCORE_CONFLICT"
        self.assertIsNone(research_score(evidence_rows(f,l,r,p))["metrics"])
