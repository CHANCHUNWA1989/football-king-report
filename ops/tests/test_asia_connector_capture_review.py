import unittest
from asia_connector_capture_review import inspect
class AsiaCaptureReviewTests(unittest.TestCase):
    def test_unpinned_bytes_rejected(self):
        with self.assertRaisesRegex(ValueError,"PIN_CHANGED"):inspect(b"{}")
