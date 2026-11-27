import io,json,unittest
from datetime import timedelta
from zipfile import ZipFile
from ops.v6_forward_archive_audit import audit,FILES
from ops.v6_forward_comparison import seal,sha
from ops.tests.test_v6_forward_comparison import inputs,NOW,KO

def archive(tamper=None):
    b,c=inputs();r=seal(b,c,NOW)
    enc=lambda x:json.dumps(x).encode()
    r["input_sha256"]=[sha(enc(b)),sha(enc(c))]
    if tamper=="record":r["rows"][0]["baseline"]=[1,0,0]
    if tamper=="input":b["predictions"][0]["ensemble_1x2"]=[1,0,0]
    f=io.BytesIO()
    with ZipFile(f,"w") as z:
        for name,value in zip(FILES,(r,b,c)):z.writestr(name,enc(value))
    return f.getvalue()
class ArchiveTests(unittest.TestCase):
    def test_ok(self):
        raw=archive();r,a=audit(raw,sha(raw),NOW+timedelta(seconds=1))
        self.assertEqual(a["sealed_count"],1)
        self.assertEqual(a["verified_forward_sample_credit"],0)
    def test_wrong_digest(self):
        with self.assertRaisesRegex(ValueError,"DIGEST"):audit(archive(),"0"*64,NOW)
    def test_input_tamper(self):
        raw=archive("input")
        with self.assertRaisesRegex(ValueError,"INPUT_DIGEST"):audit(raw,sha(raw),NOW)
    def test_record_tamper(self):
        raw=archive("record")
        with self.assertRaisesRegex(ValueError,"SEALED_RECORD"):audit(raw,sha(raw),NOW)
    def test_bad_clock(self):
        raw=archive()
        with self.assertRaisesRegex(ValueError,"CLOCK"):audit(raw,sha(raw),NOW+timedelta(minutes=11))
