import hashlib
import json
import unittest
from ops.model_divergence_evidence import evaluate_evidence, MAX_DOCUMENT


def digest(b):
    return hashlib.sha256(b).hexdigest()


def encode(rows):
    return json.dumps(rows, allow_nan=False).encode("utf-8")


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = dict(event_id="fixture", league="epl", home_id="h", away_id="a",
                            kickoff_utc="2026-11-28T17:30:00Z")
        left = dict(native_event_id="1", native_home_id="2", native_away_id="3")
        right = dict(native_event_id="4", native_home_id="5", native_away_id="6")
        self.manifest = [dict(self.fixture, left=left, right=right)]
        self.raw_a, self.raw_b = b'{"synthetic":1}', b'{"synthetic":2}'
        def row(native, provider, model, raw):
            return dict(self.fixture, **native, provider_id=provider, model_id=model,
                        source_sha256=digest(raw), source_updated_utc="2026-11-28T08:00:00Z",
                        source_captured_utc="2026-11-28T08:30:00Z",
                        information_cutoff_utc="2026-11-28T09:00:00Z",
                        prediction_utc="2026-11-28T10:00:00Z", p=[.45,.24,.31])
        self.a = row(left,"p1","A",self.raw_a)
        self.b = row(right,"p2","B",self.raw_b)
        self.doc_a, self.doc_b = encode([self.a]), encode([self.b])

    def call(self, **changes):
        kw = dict(manifest=self.manifest, left_document=self.doc_a,
                  right_document=self.doc_b, left_sha256=digest(self.doc_a),
                  right_sha256=digest(self.doc_b), left_raw={digest(self.raw_a):self.raw_a},
                  right_raw={digest(self.raw_b):self.raw_b}, left_provider="p1",
                  right_provider="p2", left_model="A", right_model="B",
                  as_of_utc="2026-11-28T12:00:00Z")
        kw.update(changes)
        r = evaluate_evidence(**kw)
        for field in ("source_authenticated","source_bytes_verified",
                      "native_identity_authenticated","model_input_derivation_verified",
                      "model_calibrated","can_recommend_bets"):
            self.assertIs(r[field],False)
        self.assertEqual(r["production_recommendations"],"DISABLED")
        return r

    def invalid(self, **changes):
        r=self.call(**changes)
        self.assertEqual(r["reason"],"INVALID_EVIDENCE_BYTES")
        self.assertEqual(r["status"],"HOLD")
        self.assertFalse(r["normalized_documents_hash_match"])
        self.assertFalse(r["raw_payload_hashes_match"])
        self.assertEqual(r["results"],[])

    def test_exact_bytes(self):
        r=self.call()
        self.assertEqual(r["status"],"RESEARCH_ONLY")
        self.assertTrue(r["normalized_documents_hash_match"])
        self.assertTrue(r["raw_payload_hashes_match"])
        self.assertEqual(r["raw_payload_count"],2)

    def test_projection_changed(self):
        self.invalid(left_document=self.doc_a+b" ")

    def test_raw_changed(self):
        self.invalid(left_raw={digest(self.raw_a):self.raw_a+b" "})

    def test_missing_or_unused_raw(self):
        self.invalid(left_raw={})
        self.invalid(left_raw={digest(self.raw_a):self.raw_a,digest(b"extra"):b"extra"})

    def test_forged_digest(self):
        self.invalid(left_sha256="a"*64)

    def test_ambiguous_json(self):
        for doc in [b'[{"p":1,"p":2}]',b'[{"x":NaN}]',b'[{"x":1e999}]',
                    b'\xff',b'{}',b'['*2000+b']'*2000]:
            with self.subTest(doc=doc[:20]):
                self.invalid(left_document=doc,left_sha256=digest(doc))

    def test_oversize(self):
        self.invalid(left_document=b"x"*(MAX_DOCUMENT+1))
        self.invalid(left_raw={digest(self.raw_a):b"x"*(MAX_DOCUMENT+1)})

    def test_wrong_types(self):
        self.invalid(left_document=bytearray(self.doc_a))
        self.invalid(left_raw=[])

    def test_hashed_wrong_identity_still_hold(self):
        doc=encode([dict(self.b,native_home_id="wrong")])
        r=self.call(right_document=doc,right_sha256=digest(doc))
        self.assertEqual(r["reason"],"INVALID_BINDING")
        self.assertEqual(r["status"],"HOLD")
        self.assertTrue(r["normalized_documents_hash_match"])

    def test_hashed_direction_conflict(self):
        doc=encode([dict(self.b,p=[.31,.24,.45])])
        r=self.call(right_document=doc,right_sha256=digest(doc))
        self.assertEqual(r["counts"],{"DIRECTION_CONFLICT":1})
        self.assertEqual(r["status"],"HOLD")

    def test_empty_sources_never_pass(self):
        doc=b"[]"
        r=self.call(left_document=doc,right_document=doc,left_sha256=digest(doc),
                    right_sha256=digest(doc),left_raw={},right_raw={})
        self.assertEqual(r["counts"],{"MISSING_PAIR":1})
        self.assertFalse(r["raw_payload_hashes_match"])
        self.assertEqual(r["status"],"HOLD")

    def test_no_payload_leak(self):
        r=self.call()
        self.assertNotIn("synthetic",str(r))
        self.assertNotIn(digest(self.raw_a),str(r))
