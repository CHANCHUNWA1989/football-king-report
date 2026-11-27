import unittest
from datetime import date
from ops.v8_ucl_alias import mapping,remap
D=date(2024,9,17)
def row(a,b,s):return (D,a,b,"ENG","ENG",1,0,s)
def doc(a="A (ENG)",b="AA (ENG)"):return {"schema":"v8-7-ucl-historical-alias-hypotheses-v1","independently_verified":False,"pairs":[{"from":a,"to":b}]}
class AliasTests(unittest.TestCase):
    def test_explicit_only(self):
        rows=[row("A (ENG)","B (ENG)","2023-24"),row("AA (ENG)","B (ENG)","2024-25")]
        m=mapping(doc(),rows)
        self.assertEqual(m,{"A (ENG)":"AA (ENG)"})
        # Two games deliberately share the synthetic date: collision must fail.
        with self.assertRaisesRegex(ValueError,"COLLISION"):remap(rows,m)
    def test_country(self):
        with self.assertRaisesRegex(ValueError,"CONFLICT"):mapping(doc(b="AA (GER)"),[])
    def test_coexistence(self):
        with self.assertRaisesRegex(ValueError,"COEXISTING"):mapping(doc(),[row("A (ENG)","AA (ENG)","2024-25")])
    def test_absent(self):
        self.assertEqual(mapping(doc(),[]),{})
    def test_remap(self):
        r=row("A (ENG)","B (ENG)","2023-24")
        self.assertEqual(remap([r],{"A (ENG)":"AA (ENG)"})[0][1],"AA (ENG)")
