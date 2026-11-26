import unittest
from datetime import datetime,timezone
from live_core_schedule_smoke import probe
class ScheduleSmokeTests(unittest.TestCase):
    def test_failure_is_not_success_and_one_request(self):
        calls=[]
        def fake(*args):calls.append(args);return None,"RATE_LIMITED"
        t=datetime(2026,11,26,tzinfo=timezone.utc)
        r=probe(fetcher=fake,now=lambda:t)
        self.assertEqual(len(calls),1)
        self.assertEqual(r["response_status"],"RATE_LIMITED")
        self.assertEqual(r["local_scheduled_rows"],0)
        self.assertEqual(r["authenticated_forward_samples"],0)
