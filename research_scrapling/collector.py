"""Isolated research-only Scrapling collector. No order or publication integration."""
import argparse
import hashlib
import json
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from scrapling import Selector

FIELDS = ("entity", "metric", "unit", "as_of", "value")
MAX_AGE = 300
MAX_SKEW = 30

def utc(s):
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("timezone required")
    return d.astimezone(timezone.utc)

def parse(page, selectors):
    result = {}
    for key in FIELDS:
        values = page.css(selectors[key]).getall()
        if len(values) != 1 or not values[0].strip():
            raise ValueError("missing or ambiguous field: " + key)
        result[key] = values[0].strip()
    result["as_of"] = utc(result["as_of"]).isoformat()
    value = Decimal(result["value"])
    if not value.is_finite():
        raise ValueError("nonfinite value")
    result["value"] = str(value.normalize())
    return result

def fetch(source):
    from scrapling.fetchers import Fetcher
    url = source["url"]
    p = urlsplit(url)
    if (source.get("approved") is not True or not source.get("permission_reference")
        or p.scheme != "https" or not p.hostname or p.username or p.password
        or p.query or p.fragment or p.port not in (None, 443)):
        raise ValueError("source not approved")
    # Only operator-reviewed static URLs; never bypass access restrictions.
    page = Fetcher.get(url, follow_redirects=False, timeout=15, retries=1,
                       stealthy_headers=False)
    if page.status != 200 or str(page.url) != url:
        raise ValueError("bad status or unexpected URL")
    raw = page.body
    if len(raw) > 2_000_000:
        raise ValueError("oversized response")
    data = parse(page, source["selectors"])
    return {"source": source["id"], "group": source["group"], "url": url,
            "captured": datetime.now(timezone.utc).isoformat(),
            "sha256": hashlib.sha256(raw).hexdigest(), "data": data}

def verify(a, b, now):
    if (not a["source"] or not b["source"] or a["source"] == b["source"]
        or not a["group"] or not b["group"] or a["group"] == b["group"]
        or urlsplit(a["url"]).hostname == urlsplit(b["url"]).hostname):
        return "HOLD_NOT_INDEPENDENT"
    for item in (a, b):
        t, c = utc(item["data"]["as_of"]), utc(item["captured"])
        if not (0 <= (now-c).total_seconds() <= MAX_AGE and
                0 <= (c-t).total_seconds() <= MAX_AGE):
            return "HOLD_TIME"
    x, y = a["data"], b["data"]
    if abs((utc(x["as_of"])-utc(y["as_of"])).total_seconds()) > MAX_SKEW:
        return "HOLD_SKEW"
    if any(x[k] != y[k] for k in ("entity", "metric", "unit")):
        return "HOLD_IDENTITY"
    return "RESEARCH_MATCH" if x["value"] == y["value"] else "HOLD_CONFLICT"

def collect(config):
    report = {"production_recommendations":"DISABLED","live_trading":"DISABLED",
              "status":"HOLD","research_only":True}
    if config.get("enabled") is not True:
        return report
    try:
        a,b = config["sources"]
        if a["group"] == b["group"] or a["id"] == b["id"]:
            raise ValueError("duplicate source group")
        first,second = fetch(a),fetch(b)
        report["status"] = verify(first,second,datetime.now(timezone.utc))
        # No raw HTML or commercial observations published in this public repo.
        report["evidence"] = [{k:v for k,v in item.items() if k!="data"}
                              for item in (first,second)]
    except Exception as e:
        report["status"] = "HOLD_COLLECTION_ERROR"
        report["error_type"] = type(e).__name__
    return report

class Tests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        stamp = self.now.isoformat()
        html = '<i id="entity">TEST</i><i id="metric">score</i><i id="unit">count</i><i id="as_of">'+stamp+'</i><i id="value">2.00</i>'
        data = parse(Selector(html),{k:"#"+k+"::text" for k in FIELDS})
        self.a = dict(source="a",group="a",url="https://a.example/",captured=stamp,data=data)
        self.b = dict(source="b",group="b",url="https://b.example/",captured=stamp,data=dict(data))
    def test_match(self):
        self.assertEqual(verify(self.a,self.b,self.now),"RESEARCH_MATCH")
    def test_conflict(self):
        self.b["data"]["value"]="3"
        self.assertEqual(verify(self.a,self.b,self.now),"HOLD_CONFLICT")
    def test_identity(self):
        self.b["data"]["entity"]="OTHER"
        self.assertEqual(verify(self.a,self.b,self.now),"HOLD_IDENTITY")
    def test_same_group(self):
        self.b["group"]="a"
        self.assertEqual(verify(self.a,self.b,self.now),"HOLD_NOT_INDEPENDENT")
    def test_same_host(self):
        self.b["url"]=self.a["url"]
        self.assertEqual(verify(self.a,self.b,self.now),"HOLD_NOT_INDEPENDENT")
    def test_stale(self):
        self.b["data"]["as_of"]="2000-01-01T00:00:00Z"
        self.assertEqual(verify(self.a,self.b,self.now),"HOLD_TIME")
    def test_disabled(self):
        r=collect({})
        self.assertEqual((r["status"],r["live_trading"],r["production_recommendations"]),("HOLD","DISABLED","DISABLED"))
    def test_missing(self):
        with self.assertRaises(ValueError):
            parse(Selector("<p>empty</p>"),{k:"#"+k+"::text" for k in FIELDS})
    def test_unapproved(self):
        with self.assertRaises(ValueError):
            fetch({"url":"https://example.org/"})

if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--config",type=Path)
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    if args.self_test:
        unittest.main(argv=["collector"],verbosity=2)
    else:
        if not args.config or not args.output:
            p.error("--config and --output required")
        result=collect(json.loads(args.config.read_text()))
        args.output.write_text(json.dumps(result,indent=2))
        if result["status"].startswith("HOLD_COLLECTION_ERROR"):
            raise SystemExit(2)
