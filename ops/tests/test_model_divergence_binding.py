import copy
import unittest
from ops.model_divergence_binding import compare

NOW = "2026-11-28T12:00:00Z"


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.base = dict(event_id="e1", league="epl", home_id="h", away_id="a",
                         kickoff_utc="2026-11-28T17:30:00Z")
        self.l = dict(native_event_id="10", native_home_id="1", native_away_id="2")
        self.r = dict(native_event_id="20", native_home_id="3", native_away_id="4")
        self.manifest = [dict(self.base, left=self.l, right=self.r)]
        def row(native, provider, model):
            return dict(self.base, **native, provider_id=provider, model_id=model,
                        source_sha256="a"*64, source_updated_utc="2026-11-28T08:00:00Z",
                        source_captured_utc="2026-11-28T08:30:00Z",
                        information_cutoff_utc="2026-11-28T09:00:00Z",
                        prediction_utc="2026-11-28T10:00:00Z", p=[.45,.24,.31])
        self.a = row(self.l,"p1","A")
        self.b = row(self.r,"p2","B")

    def run_case(self, manifest=None, a=None, b=None, **kwargs):
        m = self.manifest if manifest is None else manifest
        l = [self.a] if a is None else a
        r = [self.b] if b is None else b
        before = copy.deepcopy((m,l,r))
        opts = dict(left_provider="p1", right_provider="p2", left_model="A",
                    right_model="B", as_of_utc=NOW)
        opts.update(kwargs)
        out = compare(m,l,r,**opts)
        self.assertEqual((m,l,r),before)
        self.assertEqual(out["production_recommendations"],"DISABLED")
        self.assertFalse(out["source_authenticated"])
        self.assertFalse(out["native_identity_authenticated"])
        self.assertFalse(out["source_bytes_verified"])
        self.assertFalse(out["can_recommend_bets"])
        return out

    def test_distinct_native_ids(self):
        self.assertEqual(self.run_case()["status"],"RESEARCH_ONLY")

    def test_direction_conflict(self):
        out=self.run_case(b=[dict(self.b,p=[.31,.24,.45])])
        self.assertEqual(out["counts"],{"DIRECTION_CONFLICT":1})
        self.assertEqual(out["status"],"HOLD")

    def test_missing_pair(self):
        self.assertEqual(self.run_case(b=[])["counts"],{"MISSING_PAIR":1})

    def test_wrong_identity(self):
        for k,v in [("native_event_id","21"),("native_home_id","4"),
                    ("native_away_id","3"),("home_id","a"),("provider_id","p1"),
                    ("model_id","A"),("kickoff_utc","2026-11-28T18:00:00Z")]:
            with self.subTest(k=k):
                self.assertEqual(self.run_case(b=[dict(self.b,**{k:v})])["reason"],"INVALID_BINDING")

    def test_missing_clock_or_digest(self):
        for k in ("source_updated_utc","source_captured_utc","information_cutoff_utc","source_sha256"):
            b=dict(self.b); del b[k]
            self.assertEqual(self.run_case(b=[b])["reason"],"INVALID_BINDING")

    def test_source_time_and_digest(self):
        for k,v in [("source_updated_utc","2026-11-28T09:30:00Z"),
                    ("source_captured_utc","2026-11-28T09:01:00Z"),
                    ("source_updated_utc","2026-11-27T23:00:00Z"),
                    ("source_sha256","not-a-digest")]:
            self.assertEqual(self.run_case(b=[dict(self.b,**{k:v})])["reason"],"INVALID_BINDING")

    def test_duplicate_source_or_model(self):
        for kw in (dict(right_provider="p1"),dict(right_model="A")):
            self.assertEqual(self.run_case(**kw)["reason"],"INVALID_BINDING")

    def test_manifest_collision(self):
        m=dict(self.manifest[0],event_id="e2")
        self.assertEqual(self.run_case(manifest=self.manifest+[m])["reason"],"INVALID_BINDING")
        m=dict(m,kickoff_utc="2026-11-29T17:30:00Z")
        self.assertEqual(self.run_case(manifest=self.manifest+[m])["reason"],"INVALID_BINDING")

    def test_duplicate_row(self):
        self.assertEqual(self.run_case(a=[self.a,self.a])["status"],"HOLD")

    def test_cutoff_mismatch(self):
        out=self.run_case(b=[dict(self.b,information_cutoff_utc="2026-11-28T09:01:00Z")])
        self.assertEqual(out["counts"],{"INVALID_INPUT":1})

    def test_source_not_published(self):
        out=self.run_case(b=[dict(self.b,raw="PRIVATE_PAYLOAD")])
        self.assertNotIn("PRIVATE_PAYLOAD",str(out))
        self.assertNotIn("source_sha256",str(out))
