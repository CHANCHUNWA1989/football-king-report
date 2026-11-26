import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_live_core_statsbomb_event_replay import events
from live_core_statsbomb_cohort import inspect,index,run

def blob(raw):
    return hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()

class EventCohortTests(unittest.TestCase):
    def test_private_event_replay(self):
        raw=json.dumps(events()).encode()
        r=inspect(raw,blob(raw),1,2)
        self.assertEqual(r["regulation_cards"],1)
        self.assertEqual(r["elapsed_minutes_by_half"],[45,45])
        self.assertEqual(r["elapsed_beyond_45_by_half"],[0,0])
        self.assertEqual(len(r["buckets"]),2)

    def test_private_context_projection_does_not_claim_on_pitch_verification(self):
        e=events()
        e[2]["shot"]["outcome"]={"name":"Saved"}
        e[3]["position"]={"id":1,"name":"Goalkeeper"}
        raw=json.dumps(e).encode()
        r=inspect(raw,blob(raw),1,2)
        self.assertEqual((r["home_id"],r["away_id"]),(1,2))
        self.assertEqual(r["score_immediately_before_dismissal"],[0,0])
        self.assertEqual(r["single_dismissal_event"]["position_at_dismissal"],"GOALKEEPER")
        self.assertFalse(r["actual_on_pitch_verified"])
        self.assertNotIn("dismissal_player_context",r)

    def test_frozen_public_metadata_scope(self):
        from live_core_statsbomb_wc2022_pins import EVENT_BLOBS,INDEX_BLOB,UPSTREAM_TREE
        self.assertEqual(len(EVENT_BLOBS),64)
        self.assertEqual(INDEX_BLOB,"7e259140298f3de247ab94f1f4e026619c0f612b")
        self.assertEqual(len(UPSTREAM_TREE),40)
        self.assertTrue(all(len(pin)==40 and 0<size<=12000000
                            for pin,size in EVENT_BLOBS.values()))

    def test_wrong_blob_rejected(self):
        raw=json.dumps(events()).encode()
        with self.assertRaisesRegex(ValueError,"BLOB_MISMATCH"):
            inspect(raw,"0"*40,1,2)

    def test_short_half_rejected(self):
        e=events()
        e[5]["timestamp"]="00:44:00.000"
        raw=json.dumps(e).encode()
        with self.assertRaisesRegex(ValueError,"SHORT_PERIOD"):
            inspect(raw,blob(raw),1,2)

    def test_index_and_missing_fixture(self):
        raw=json.dumps([{"match_id":1,"match_date":"2022-11-20","home_team":{"home_team_id":1},"away_team":{"away_team_id":2}},
                        {"match_id":2,"match_date":"2022-11-21","home_team":{"home_team_id":1},"away_team":{"away_team_id":2}}]).encode()
        event=json.dumps(events()).encode()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"matches.json").write_bytes(raw)
            (root/"1.json").write_bytes(event)
            manifest={"schema":"statsbomb-private-wc2022-v1","rights_confirmed":True,"event_blob_pins":{"1":blob(event),"2":blob(event)}}
            (root/"manifest.json").write_text(json.dumps(manifest))
            with patch("live_core_statsbomb_cohort.INDEX_PIN",blob(raw)),patch("live_core_statsbomb_cohort.INDEX_COUNT",2),patch("live_core_statsbomb_cohort.EVENT_BLOBS",{"1":(blob(event),len(event)),"2":(blob(event),len(event))}):
                result=run(root)
                self.assertEqual(result["accepted"],1)
                self.assertEqual(result["rejected_match_ids"],[2])
                self.assertEqual(result["rejection_counts"],{"PRIVATE_FILE":1})
                self.assertEqual(result["event_revisions_pinned"],2)
                manifest["event_blob_pins"]["1"]="0"*40
                (root/"manifest.json").write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError,"UNPINNED_EVENT_REVISION"):run(root)
                manifest["event_blob_pins"]["1"]=blob(event)
                (root/"manifest.json").write_text(json.dumps(manifest))
                (root/"1.json").write_bytes(event+b" ")
                self.assertEqual(run(root)["rejection_counts"],{"EVENT_BYTE_LENGTH":1,"PRIVATE_FILE":1})
                self.assertFalse(result["complete_cohort"])
                self.assertFalse(result["red_card_effect_calibrated"])
                self.assertEqual(result["production_recommendations"],"DISABLED")
                manifest["event_blob_pins"].pop("2")
                (root/"manifest.json").write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError,"COHORT_MANIFEST_SCOPE"):run(root)
