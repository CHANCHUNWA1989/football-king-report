"""Bounded, research-only OSV query for the verified public PyPI inventory."""
import argparse
import hashlib
import json
import re
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler

URL = 'https://api.osv.dev/v1/querybatch'
LIMIT = 512000


def unique(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError('duplicate JSON key')
        out[k] = v
    return out


def inventory(raw):
    if len(raw) > 8192:
        raise ValueError('oversized inventory')
    result = {}
    for line in raw.decode('ascii').splitlines():
        match = re.fullmatch(r'([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)', line)
        if not match:
            raise ValueError('invalid inventory')
        name = re.sub(r'[-_.]+', '-', match[1]).lower()
        if name in result:
            raise ValueError('duplicate package')
        result[name] = match[2]
    if len(result) != 23 or result.get('scrapling') != '0.4.6':
        raise ValueError('unexpected inventory')
    return sorted(result.items())


def parse(raw, packages):
    if len(raw) > LIMIT:
        raise ValueError('oversized response')
    obj = json.loads(raw, object_pairs_hook=unique)
    if type(obj) is not dict or set(obj) != {'results'} or type(obj['results']) is not list or len(obj['results']) != len(packages):
        raise ValueError('incomplete batch')
    findings = []
    for (name, version), row in zip(packages, obj['results']):
        if type(row) is not dict or not set(row) <= {'vulns', 'next_page_token'} or row.get('next_page_token', '') != '':
            raise ValueError('incomplete or unexpected result')
        vulns = row.get('vulns', [])
        if type(vulns) is not list:
            raise ValueError('invalid vulnerabilities')
        ids = set()
        for item in vulns:
            if type(item) is not dict or not isinstance(item.get('id'), str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', item['id']):
                raise ValueError('invalid advisory ID')
            ids.add(item['id'])
        if ids:
            findings.append({'package':name,'version':version,'advisory_ids':sorted(ids)})
    return findings


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('redirect refused')


def query(packages):
    payload = json.dumps({'queries':[{'package':{'ecosystem':'PyPI','name':n},'version':v} for n,v in packages]}).encode()
    req = Request(URL, data=payload, headers={'Content-Type':'application/json','Accept':'application/json','User-Agent':'ScraplingResearchAudit/1.0'})
    with build_opener(NoRedirect()).open(req, timeout=20) as response:
        if response.status != 200 or response.geturl() != URL:
            raise ValueError('unexpected HTTP response')
        return response.read(LIMIT+1)


def main(path, output):
    result = dict(schema='scrapling-osv-audit-v1',status='HOLD',model_input_allowed=False,live_trading='DISABLED',production_recommendations='DISABLED',scope='23_PYPI_PACKAGES_ONLY',os_packages_scanned=False,wheel_hash_verified=False,scan_completed=False,verdict='INCOMPLETE',source=URL,started_utc=datetime.now(timezone.utc).isoformat())
    try:
        with path.open('rb') as stream:
            raw = stream.read(8193)
        packages = inventory(raw)
        result['inventory_sha256'] = hashlib.sha256(raw).hexdigest()
        response = query(packages)
        findings = parse(response, packages)
        result.update(scan_completed=True,packages_checked=len(packages),response_sha256=hashlib.sha256(response).hexdigest(),findings=findings,verdict='ADVISORIES_FOUND' if findings else 'NO_KNOWN_ADVISORIES_RETURNED')
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        result['error_type'] = type(exc).__name__
    result['finished_utc'] = datetime.now(timezone.utc).isoformat()
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    return int(result['verdict'] != 'NO_KNOWN_ADVISORIES_RETURNED')


class Tests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(parse(b'{"results":[{}]}',[('a','1')]),[])
    def test_advisory(self):
        self.assertEqual(parse(b'{"results":[{"vulns":[{"id":"GHSA-test"}]}]}',[('a','1')])[0]['advisory_ids'],['GHSA-test'])
    def test_invalid(self):
        for raw in (b'{}',b'{"results":[]}',b'{"results":[{"next_page_token":"more"}]}',b'{"results":[{"vulns":null}]}',b'{"results":[{"vulns":[{}]}]}',b'{"results":[{"vulns":[],"vulns":[]}]}',b'x'*(LIMIT+1)):
            with self.subTest(size=len(raw)):
                with self.assertRaises(ValueError):
                    parse(raw,[('a','1')])
    def test_duplicate_inventory(self):
        with self.assertRaises(ValueError):
            inventory(b'a==1\nA==1\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--self-test', action='store_true')
    p.add_argument('--inventory', type=Path)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    if a.self_test:
        unittest.main(argv=['osv_audit'], verbosity=2)
    if not a.inventory or not a.output:
        p.error('inventory and output required')
    raise SystemExit(main(a.inventory,a.output))
