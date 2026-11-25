import unittest
from ops.v8_ucl_gap_fill import parse,compare
class GapTests(unittest.TestCase):
    def test_bad_date(self):
        raw="▪ League, Matchday 1\n Mon Sep 16 2025\n A (ENG) v B (GER) 1-0\n".encode()
        with self.assertRaisesRegex(ValueError,"DATE_CONFLICT"):parse(raw,"2025-26")
    def test_bad_score(self):
        raw="▪ League, Matchday 1\n Tue Sep 16 2025\n A (ENG) v B (GER) 1-0 a.e.t.\n".encode()
        with self.assertRaisesRegex(ValueError,"UNPARSED"):parse(raw,"2025-26")
    def test_incomplete(self):
        raw="▪ Gruppe G\n Tue Oct 20 2020\n A (ENG) v B (GER) 1-0\n".encode()
        with self.assertRaisesRegex(ValueError,"INCOMPLETE"):parse(raw,"2020-21")
    def test_overlap_conflict(self):
        with self.assertRaisesRegex(ValueError,"OVERLAP_CONFLICT"):compare([],[])
    def test_duplicate(self):
        raw="▪ League, Matchday 1\n Tue Sep 16 2025\n A (ENG) v B (GER) 1-0\n A (ENG) v B (GER) 1-0\n".encode()
        with self.assertRaisesRegex(ValueError,"INVALID_MATCH"):parse(raw,"2025-26")
