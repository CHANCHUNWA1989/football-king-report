import copy
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from ops.research_unified_cutoff_v39 import audit_batch
from ops.research_unified_prematch_replay_v35 import freeze
from ops.research_unified_prematch_audit_v34 import Forecast
from ops.research_market_provenance_v1 import Quote

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026,11,27,12,tzinfo=timezone.utc)
KICK = NOW + timedelta(hours=3)

def record(e, frozen=NOW, quote_time=None, forecast_time=None):
    qt = frozen if quote_time is None else quote_time
    ft = frozen if forecast_time is None else forecast_time
    fs=[Forecast(e,KICK,ft,"m"+str(i),"f"+str(i),1.5+i*.1,1.1)
        for i in range(2)]
    qs=[Quote("p"+str(i),"book",e,m,s,l,1.9,qt,KICK,
              upstream_provider="u"+str(i))
        for m,s,l in [("handicap","home",-.25),("handicap","away",-.25),
                      ("totals","over",2.75),("totals","under",2.75)]
        for i in range(2)]
    return freeze(event_id=e,kickoff=KICK,now=frozen,forecasts=fs,quotes=qs,
                  handicap_line=-.25,totals_line=2.75,root=ROOT)

class CutoffV39(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a,cls.b=record("a"),record("b")
        cls.roster={"a":KICK.isoformat(),"b":KICK.isoformat()}

    def check(self, roster, records, *, cutoff=NOW.isoformat(), ok=False):
        r=audit_batch(roster,records,cutoff=cutoff,root=ROOT)
        self.assertIs(r["cutoff_verified"],ok)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        for k in ("source_identity_authenticated","roster_authenticated",
                  "external_timestamp_verified","training_admission",
                  "qualified_for_production","verified_executable_ev"):
            self.assertIs(r[k],False)
        self.assertEqual(r["local_batch_sha256"] is not None,ok)
        return r

    def test_valid_batch_order_and_timezone(self):
        a=self.check(self.roster,[self.a,self.b],ok=True)
        tz=timezone(timedelta(hours=8))
        b=self.check({"b":KICK.astimezone(tz).isoformat(),"a":KICK.isoformat()},
                     [self.b,self.a],cutoff=NOW.astimezone(tz).isoformat(),ok=True)
        self.assertEqual(a["local_batch_sha256"],b["local_batch_sha256"])

    def test_cutoff_300_seconds_inclusive(self):
        self.check(self.roster,[self.a,self.b],
                   cutoff=(NOW+timedelta(seconds=300)).isoformat(),ok=True)

    def test_stale_snapshot(self):
        self.check(self.roster,[self.a,self.b],
                   cutoff=(NOW+timedelta(seconds=301)).isoformat())

    def test_future_snapshot(self):
        self.check(self.roster,[self.a,self.b],
                   cutoff=(NOW-timedelta(seconds=1)).isoformat())

    def test_stale_quote_despite_fresh_snapshot(self):
        b=record("b",quote_time=NOW-timedelta(seconds=299))
        self.check(self.roster,[self.a,b],
                   cutoff=(NOW+timedelta(seconds=2)).isoformat())

    def test_stale_forecast_despite_fresh_snapshot(self):
        b=record("b",forecast_time=NOW-timedelta(seconds=86399))
        self.check(self.roster,[self.a,b],
                   cutoff=(NOW+timedelta(seconds=2)).isoformat())

    def test_kickoff_mismatch(self):
        self.check(dict(self.roster,b=(KICK+timedelta(minutes=1)).isoformat()),
                   [self.a,self.b])

    def test_started_at_cutoff(self):
        self.check(self.roster,[self.a,self.b],cutoff=KICK.isoformat())

    def test_missing_duplicate_tampered(self):
        bad=copy.deepcopy(self.b)
        bad["quotes"][0]["decimal_odds"]=3
        for records in ([self.a],[self.a,self.a],[self.a,bad]):
            with self.subTest(size=len(records)):
                self.check(self.roster,records)

    def test_invalid_roster_or_clock(self):
        for roster in ({},[],{" a":KICK.isoformat()},{"a":"2026-11-27T15:00:00"}):
            self.check(roster,[self.a])
        for cutoff in ("2026-11-27T12:00:00",None,"bad"):
            self.check(self.roster,[self.a,self.b],cutoff=cutoff)

if __name__=="__main__":
    unittest.main()
