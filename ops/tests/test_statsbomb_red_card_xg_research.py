import json
import hashlib
import unittest
from ops.statsbomb_red_card_xg_research import summarize


def fixture():
    def event(i,kind,period,clock,team=1,**extra):
        return {"id":str(i),"index":i,"type":{"name":kind},"period":period,
                "timestamp":clock,"team":{"id":team},**extra}
    def shot(i,period,clock,team,xg):
        return event(i,"Shot",period,clock,team,shot={"statsbomb_xg":xg,
            "outcome":{"name":"Saved"},"type":{"name":"Open Play"}})
    events=[shot(1,1,"00:10:00.000",1,.2),
            event(2,"Half End",1,"00:47:00.000"),
            shot(3,2,"00:05:00.000",2,.3),
            event(4,"Foul Committed",2,"00:15:00.500",1,
                  player={"id":11},foul_committed={"card":{"name":"Red Card"}}),
            shot(5,2,"00:20:00.000",2,.4),
            shot(6,2,"00:21:00.000",1,.1),
            event(7,"Half End",2,"00:50:00.000")]
    lineup=[{"team_id":1,"lineup":[{"player_id":11,"cards":[{"card_type":"Red Card",
              "time":"60:00","period":2}]}]},
            {"team_id":2,"lineup":[{"player_id":22,"cards":[]}]}]
    return events,lineup


def run(events,lineups):
    raw=[json.dumps(x).encode() for x in (events,lineups)]
    rec={"match_id":100,"home_team_id":1,"away_team_id":2}
    for name,b,data in zip(("events","lineups"),raw,(events,lineups)):
        rec[name]={"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest(),"records":len(data)}
    return summarize(*raw,rec)


class RedCardXGTests(unittest.TestCase):
    def test_clock_exposure_and_xg(self):
        e,l=fixture()
        r=run(e,l)
        self.assertEqual(r["reason"],"SINGLE_PROVIDER_POSTMATCH_DESCRIPTIVE_ONLY")
        self.assertEqual(r["before_elapsed_seconds"],3720.5)
        self.assertEqual(r["after_elapsed_seconds"],2099.5)
        self.assertAlmostEqual(r["teams"]["2"]["after"]["xg"],.4)
        self.assertEqual(r["teams"]["1"]["before"]["shots"],1)
        self.assertFalse(r["causal_effect_estimated"])
        self.assertFalse(r["independent_source_verified"])
        self.assertEqual(r["certified_prospective_samples"],0)

    def test_missing_or_conflicting_card(self):
        e,l=fixture()
        l[0]["lineup"][0]["cards"]=[]
        self.assertEqual(run(e,l)["reason"],"UNSUPPORTED_OR_CONFLICTING_CARD_COUNTS")
        e.pop(3)
        self.assertEqual(run(e,l)["reason"],"NO_DISMISSAL_RECORDED")

    def test_identity_and_clock_mismatch(self):
        e,l=fixture()
        l[0]["lineup"][0]["cards"][0]["time"]="61:00"
        self.assertEqual(run(e,l)["reason"],"CARD_CLOCK_MISMATCH")
        e,l=fixture()
        l[0]["lineup"][0]["player_id"]=99
        self.assertEqual(run(e,l)["reason"],"CARD_IDENTITY_OR_PERIOD_MISMATCH")

    def test_conflicting_shot_order_and_half_end(self):
        e,l=fixture()
        e[4]["timestamp"]="00:10:00.000"
        self.assertEqual(run(e,l)["reason"],"SHOT_EVENT_ORDER_CONFLICT")
        e,l=fixture()
        e.pop()
        self.assertEqual(run(e,l)["reason"],"MISSING_OR_CONFLICTING_HALF_END_CLOCK")

    def test_duplicate_index_and_invalid_xg(self):
        e,l=fixture()
        e[-1]["index"]=1
        with self.assertRaises(ValueError):
            run(e,l)
        e,l=fixture()
        e[0]["shot"]["statsbomb_xg"]=True
        with self.assertRaises(ValueError):
            run(e,l)


if __name__=="__main__":
    unittest.main()
