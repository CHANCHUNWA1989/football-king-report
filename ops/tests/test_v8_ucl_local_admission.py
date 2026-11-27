import json,unittest
from ops.v8_ucl_local_admission import admit,sha,map_ids
from ops.v5_ucl_source_gate import FD
from ops.tests.test_v8_ucl_current_intake import NOW,fdrow
def inputs():
    raw=json.dumps({"competition":{"code":"CL"},"matches":[fdrow()]}).encode()
    meta={"schema":"v8-6-ucl-authorized-capture-v1","source":FD,"payload_sha256":sha(raw),"season":2026,"captured_utc":NOW.isoformat()}
    m={"schema":"v8-6-ucl-historical-label-map-v1","pairs":[{"football_data_team_id":2,"historical_label":"A (ENG)","evidence_reference":"https://example.org/a"},{"football_data_team_id":3,"historical_label":"B (GER)","evidence_reference":"https://example.org/b"}]}
    return raw,meta,m
class LocalAdmissionTests(unittest.TestCase):
    def test_valid_but_unqualified(self):
        r=admit(*inputs(),NOW)
        self.assertEqual(r["local_future_candidate_count"],1)
        self.assertEqual(r["qualified_model_inputs"],0)
        self.assertEqual(r["production_recommendations"],"DISABLED")
    def test_bad_hash(self):
        a,b,c=inputs()
        with self.assertRaisesRegex(ValueError,"INTEGRITY"):admit(a+b" ",b,c,NOW)
    def test_unmapped(self):
        a,b,c=inputs();c["pairs"].pop()
        r=admit(a,b,c,NOW)
        self.assertEqual(r["unmapped_fixtures"],1)
        self.assertEqual(r["local_future_candidate_count"],0)
    def test_duplicate_label(self):
        a,b,c=inputs();c["pairs"][1]["historical_label"]=c["pairs"][0]["historical_label"]
        with self.assertRaisesRegex(ValueError,"MAP_CONFLICT"):admit(a,b,c,NOW)
    def test_wrong_source(self):
        a,b,c=inputs();b["source"]="https://example.org"
        with self.assertRaisesRegex(ValueError,"INTEGRITY"):admit(a,b,c,NOW)
