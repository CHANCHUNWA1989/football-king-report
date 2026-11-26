import unittest
from copy import deepcopy
from hashlib import sha256
from json import dumps
from ops.historical_event_intake_20261127 import intake

def event(i,t,kind="SHOT",side="home",xg=.2):
    return dict(event_id=str(i),elapsed_play_seconds=t,sequence=i,kind=kind,side=side,shot_xg=xg)

def run(events,cutoff=100,**kwargs):
    raw=dumps(dict(fixture_id="f",source_id="s",events=events)).encode()
    opts=dict(expected_sha256=sha256(raw).hexdigest(),fixture_id="f",source_id="s",cutoff_seconds=cutoff)
    opts.update(kwargs)
    return intake(raw,**opts)

class IntakeTests(unittest.TestCase):
    def test_exclusive_cutoff(self):
        events=[event(1,10),event(2,99,"ON_FIELD_DISMISSAL","away"),
                event(3,100,xg=.9),event(4,101,side="away",xg=.8)]
        r=run(events)
        self.assertEqual(r["events_before_cutoff"],2)
        self.assertEqual(r["shot_counts"],{"home":1,"away":0})
        self.assertEqual(r["historical_cumulative_shot_xg"],{"home":.2,"away":0})
        self.assertEqual(r["on_field_dismissals"],{"home":0,"away":1})
        for k in ("license_verified","availability_attested","live_xg_verified","qualified"):
            self.assertFalse(r[k])
    def test_future_data_invariance(self):
        for cutoff in range(0,601,10):
            events=[event(i,i*10,side=("home" if i%2 else "away")) for i in range(61)]
            altered=deepcopy(events)
            for e in altered:
                if e["elapsed_play_seconds"]>=cutoff:
                    e["shot_xg"]=.95
            a,b=run(events,cutoff),run(altered,cutoff)
            for k in ("shot_counts","historical_cumulative_shot_xg","on_field_dismissals"):
                self.assertEqual(a[k],b[k])
    def test_fail_closed(self):
        for events in ([event(1,5),event(1,6)],[event(1,10),event(2,9)],
                       [event(1,5,xg=None)],[event(1,5,xg=True)],
                       [event(1,5,xg=1.1)],[event(1,5,kind="RED_CARD")],
                       [event(1,5,side="unknown")],[event(1,-1)]):
            with self.subTest(events=events),self.assertRaises(ValueError):
                run(events)
        for kwargs in (dict(expected_sha256="bad"),dict(source_id="other"),
                       dict(fixture_id="other"),dict(cutoff_seconds=True)):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                run([],**kwargs)
    def test_missing_xg_not_zero(self):
        e=event(1,5);del e["shot_xg"]
        with self.assertRaises(ValueError): run([e])
    def test_zero_observations(self):
        r=run([],0)
        self.assertEqual(r["events_before_cutoff"],0)
        self.assertFalse(r["availability_attested"])

if __name__=="__main__": unittest.main()
