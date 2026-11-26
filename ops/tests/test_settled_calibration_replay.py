import json
import hashlib
import unittest
from unittest.mock import patch
from settled_calibration_replay import replay
class SettledReplayTests(unittest.TestCase):
    def test_wrong_bytes_rejected(self):
        with self.assertRaisesRegex(ValueError,"LEDGER_PIN_CHANGED"):
            replay(b"{}")
    def test_count_mismatch_rejected_even_with_matching_pin(self):
        raw=json.dumps({"production_recommendations":"DISABLED","samples":[],"n":1}).encode()
        pin=hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()
        with patch("settled_calibration_replay.PIN",pin), self.assertRaisesRegex(ValueError,"UNSAFE_LEDGER"):
            replay(raw)
