"""Synthetic chronological replay coverage; no real match evidence."""
import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_vnext_native_prematch_bridge import archive, bridge, KO
from test_vnext_live_evidence_cut import sample, stamp, NOW
from vnext_live_evidence_cut import cut_digest
from vnext_native_series_replay import replay_series

def case():
    doc=archive()
    raw=json.dumps(doc).encode()
    digest=hashlib.sha256(raw).hexdigest()
    pre=bridge(doc)
    e,s=sample()
    fid=pre["fixture_id"]
    for key in ("a","b","previous_a","previous_b"):
        e[key]["fixture_id"]=fid
    e["model"]["fixture_id"]=e["model"]["event_consensus"]["fixture_id"]=fid
    e["model"]["prematch"]=pre
    s["event_id"]=fid
    for k in ("score","stats","quote"):
        s[k]["event_id"]=fid
    first=dict(envelope=e,snapshot=s,expected_digest=cut_digest(e,s),decision_epoch=NOW)
    second=copy.deepcopy(first)
    e2,s2=second["envelope"],second["snapshot"]
    second["decision_epoch"]=e2["decision_epoch"]=NOW+60
    for key in ("a","b"):
        e2["previous_"+key]=copy.deepcopy(e[key])
        e2[key]["minute"]+=1
        e2[key]["observed"]+=60
        e2[key]["received"]+=60
    e2["model"]["minute_elapsed"]+=1
    e2["model"]["decision_utc"]=e2["model"]["event_consensus"]["decision_utc"]=stamp(NOW+60)
    s2["decision_utc"]=stamp(NOW+60)
    s2["score"]["minute"]+=1
    s2["score"]["upstream_updated_utc"]=stamp(e2["a"]["observed"])
    s2["score"]["captured_utc"]=stamp(e2["a"]["received"])
    for k in ("stats","quote"):
        s2[k]["upstream_updated_utc"]=stamp(NOW+56)
        s2[k]["captured_utc"]=stamp(NOW+58)
    second["expected_digest"]=cut_digest(e2,s2)
    return raw,digest,[first,second]

def run(raw,digest,cuts):
    return replay_series(raw,digest,fixture_id="openligadb:123",
        home_native_id="10",away_native_id="20",kickoff_utc=KO,cuts=cuts)

def resign(cut):
    cut["expected_digest"]=cut_digest(cut["envelope"],cut["snapshot"])

class SeriesTests(unittest.TestCase):
    def test_two_cuts_share_prematch_and_normalized_probabilities(self):
        raw,digest,cuts=case()
        out=run(raw,digest,cuts)
        self.assertEqual(out["series_status"],"STRUCTURAL_RESEARCH_ONLY")
        self.assertEqual(out["cut_count"],2)
        self.assertEqual(out["production_recommendations"],"DISABLED")
        self.assertEqual(out["verified_forward_sample_credit"],0)
        for cut in out["cuts"]:
            self.assertAlmostEqual(sum(cut["research_diagnostics"]["probabilities_1x2"].values()),1)
        self.assertFalse(out["historical_clock_attested"])
        self.assertIsNone(out["model_edge"])
    def test_changed_prematch_with_recomputed_digest_rejected(self):
        raw,digest,cuts=case()
        cuts[1]["envelope"]["model"]["prematch"]["expected_home_goals"]=3.0
        resign(cuts[1])
        out=run(raw,digest,cuts)
        self.assertEqual(out["reason"],"PREMATCH_ARCHIVE_MISMATCH")
        self.assertNotIn("cuts",out)
    def test_reverse_duplicate_and_discontinuous_history_rejected(self):
        raw,digest,cuts=case()
        for seq in (cuts[::-1],[cuts[0],cuts[0]]):
            self.assertEqual(run(raw,digest,seq)["reason"],"SERIES_CLOCK_ORDER")
        cuts[1]["envelope"]["previous_a"]["received"]-=1
        resign(cuts[1])
        out=run(raw,digest,cuts)
        self.assertEqual(out["reason"],"SERIES_HISTORY_DISCONTINUITY")
        self.assertNotIn("cuts",out)
    def test_tampered_second_cut_drops_all_outputs(self):
        raw,digest,cuts=case()
        cuts[1]["snapshot"]["quote"]["decimal_price"]=2.1
        out=run(raw,digest,cuts)
        self.assertEqual(out["reason"],"SERIES_EVIDENCE_REJECTED")
        self.assertNotIn("cuts",out)
        self.assertFalse(out["positive_ev_verified"])
    def test_red_card_update_remains_research_only(self):
        raw,digest,cuts=case()
        e,s=cuts[1]["envelope"],cuts[1]["snapshot"]
        for key in ("a","b"):
            e[key]["red_home"]=1
        e["model"]["red_home"]=1
        e["model"]["event_consensus"]["active_red_cards"]["HOME"]=1
        s["score"]["red_home"]=1
        s["score"]["last_material_event_utc"]=stamp(NOW+40)
        resign(cuts[1])
        out=run(raw,digest,cuts)
        self.assertEqual(out["cut_count"],2)
        self.assertEqual(out["cuts"][1]["red_cards"],[1,0])
        self.assertFalse(out["source_authenticated"])
        self.assertEqual(out["verified_forward_sample_credit"],0)

    def test_archive_kickoff_cannot_change_even_with_recomputed_cut(self):
        raw,digest,cuts=case()
        for index in (0,1):
            with self.subTest(index=index):
                changed=copy.deepcopy(cuts)
                cut=changed[index]
                cut["envelope"]["model"]["kickoff_utc"]="2026-11-03T20:01:00Z"
                cut["snapshot"]["kickoff_utc"]="2026-11-03T20:01:00Z"
                resign(cut)
                out=run(raw,digest,changed)
                self.assertEqual(out["reason"],"SERIES_KICKOFF_MISMATCH")
                self.assertNotIn("cuts",out)
                self.assertEqual(out["production_recommendations"],"DISABLED")
        # Equivalent explicit offset is not a different kickoff.
        cuts[0]["envelope"]["model"]["kickoff_utc"]="2026-11-04T04:00:00+08:00"
        resign(cuts[0])
        self.assertEqual(run(raw,digest,cuts)["series_status"],"STRUCTURAL_RESEARCH_ONLY")
