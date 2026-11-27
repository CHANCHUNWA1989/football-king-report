import unittest
from datetime import date
from ops.v9_history_expansion import expected,combine,load
from ops.v8_multiseason import parse
import json
class ExpansionTests(unittest.TestCase):
    def test_scope(self):
        self.assertIn("2010-11/en.1.json",expected())
        self.assertIn("2020-21/pt.1.json",expected())
        self.assertNotIn("2010-11/pt.1.json",expected())
        self.assertNotIn("2021-22/en.1.json",expected())
    def test_overlap(self):
        with self.assertRaisesRegex(ValueError,"OVERLAPPING"):combine({("2010-11","en.1"):[]},{("2010-11","en.1"):[]})
    def test_duplicate(self):
        r=(date(2011,1,1),"A","B",1,0)
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):combine({("2010-11","en.1"):[r]},{("2011-12","en.1"):[r]})
    def test_disjoint(self):
        r=(date(2011,1,1),"A","B",1,0)
        a=combine({("2010-11","en.1"):[r]},{("2010-11","de.1"):[r]})
        self.assertEqual(len(a),2)
    def test_missing(self):
        raw=json.dumps({"matches":[{"date":"2019-09-01","team1":"A","team2":"B","score":{"ft":[2,0]}},{"date":"2020-05-01","team1":"B","team2":"A","score":{},"status":"cancelled"}]}).encode()
        rows,n,total=parse(raw,"2019-20")
        self.assertEqual((len(rows),n,total),(1,1,2))
    def test_manifest(self):
        with self.assertRaisesRegex(ValueError,"MANIFEST"):load("/unused",{"files":[]})
