"""Research-only Debian source-package inventory and bounded OSV audit."""
import argparse
import hashlib
import json
import re
import subprocess
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, build_opener
from osv_audit import NoRedirect, URL, LIMIT, parse, unique

MAX_PACKAGES = 400
BATCH = 50
MAX_INVENTORY = 128000


def release(raw):
    fields = {}
    for line in raw.splitlines():
        if line.startswith(('ID=', 'VERSION_ID=')):
            key, value = line.split('=', 1)
            if key in fields:
                raise ValueError('duplicate OS release field')
            fields[key] = value.strip('"')
    if fields.get('ID') != 'debian' or fields.get('VERSION_ID') not in ('12', '13'):
        raise ValueError('unreviewed Debian release')
    return 'Debian:' + fields['VERSION_ID']


def package_pairs(raw):
    if len(raw) > MAX_INVENTORY:
        raise ValueError('inventory too large')
    rows, names = set(), set()
    for line in raw.decode('ascii').splitlines():
        parts = line.split('\t')
        if len(parts) != 5:
            raise ValueError('invalid dpkg row')
        status, binary, version, source, source_version = parts
        if status in ('deinstall ok config-files', 'purge ok not-installed'):
            continue
        if status not in ('install ok installed', 'hold ok installed'):
            raise ValueError('unexpected package state')
        if (not re.fullmatch(r'[a-z0-9][a-z0-9+.-]*(?::[a-z0-9-]+)?', binary)
                or not re.fullmatch(r'[a-z0-9][a-z0-9+.-]*', source)
                or not all(re.fullmatch(r'[0-9][A-Za-z0-9.+:~\-]*', v) for v in (version, source_version))
                or binary in names):
            raise ValueError('invalid or duplicate package')
        names.add(binary)
        rows.add((source, source_version))
    if not 0 < len(rows) <= MAX_PACKAGES:
        raise ValueError('unsupported source package count')
    return sorted(rows), len(names)


def capture():
    ecosystem = release(Path('/etc/os-release').read_text(encoding='utf-8'))
    raw = subprocess.check_output(['dpkg-query', '-W', '-f=${Status}\t${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\n'], timeout=15)
    pairs, count = package_pairs(raw)
    return {'ecosystem':ecosystem, 'binary_count':count, 'raw_dpkg':raw.decode('ascii'), 'source_packages':len(pairs)}


def query(ecosystem, pairs):
    payload = json.dumps({'queries':[{'package':{'ecosystem':ecosystem,'name':n},'version':v} for n,v in pairs]}).encode()
    req = Request(URL, data=payload, headers={'Content-Type':'application/json','Accept':'application/json','User-Agent':'ScraplingResearchAudit/1.0'})
    with build_opener(NoRedirect()).open(req, timeout=20) as response:
        if response.status != 200 or response.geturl() != URL:
            raise ValueError('unexpected HTTP response')
        return response.read(LIMIT+1)


def audit(path, output):
    report = dict(schema='scrapling-debian-audit-v1', status='HOLD', model_input_allowed=False, live_trading='DISABLED', production_recommendations='DISABLED', scan_completed=False, verdict='INCOMPLETE', scope='DPKG_SOURCE_PACKAGES_ONLY', started_utc=datetime.now(timezone.utc).isoformat(), findings=[], batches=[])
    try:
        with path.open('rb') as stream:
            raw = stream.read(MAX_INVENTORY*2+1)
        if len(raw)>MAX_INVENTORY*2:
            raise ValueError('oversized JSON')
        doc = json.loads(raw, object_pairs_hook=unique)
        if type(doc) is not dict or set(doc) != {'ecosystem','binary_count','raw_dpkg','source_packages'} or doc['ecosystem'] not in ('Debian:12','Debian:13'):
            raise ValueError('invalid inventory envelope')
        pairs, count = package_pairs(doc['raw_dpkg'].encode('ascii'))
        if type(doc['binary_count']) is not int or type(doc['source_packages']) is not int or count != doc['binary_count'] or len(pairs) != doc['source_packages']:
            raise ValueError('inventory counts mismatch')
        report.update(ecosystem=doc['ecosystem'], binary_count=count, source_packages=len(pairs), inventory_sha256=hashlib.sha256(raw).hexdigest())
        for offset in range(0,len(pairs),BATCH):
            batch = pairs[offset:offset+BATCH]
            response = query(doc['ecosystem'],batch)
            findings = parse(response,batch)
            evidence = output.with_name(output.stem+'-batch-'+str(offset//BATCH)+'.json')
            with evidence.open('xb') as stream:
                stream.write(response)
            report['batches'].append({'offset':offset,'count':len(batch),'response_file':evidence.name,'sha256':hashlib.sha256(response).hexdigest()})
            report['findings'].extend(findings)
        report.update(scan_completed=True, verdict='ADVISORIES_FOUND' if report['findings'] else 'NO_KNOWN_ADVISORIES_RETURNED')
    except (OSError,ValueError,TypeError,AttributeError,RecursionError) as exc:
        report['error_type'] = type(exc).__name__
    report['finished_utc']=datetime.now(timezone.utc).isoformat()
    output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return int(report['verdict'] != 'NO_KNOWN_ADVISORIES_RETURNED')


class Tests(unittest.TestCase):
    def test_release(self):
        self.assertEqual(release('ID=debian\nVERSION_ID="13"'),'Debian:13')
        for raw in ('ID=ubuntu\nVERSION_ID=13','ID=debian\nVERSION_ID=14','ID=debian\nID=debian\nVERSION_ID=13'):
            with self.assertRaises(ValueError): release(raw)
    def test_source_dedup(self):
        raw=b'install ok installed\tlibfoo:amd64\t1.2+b1\tfoo\t1.2\nhold ok installed\tfoo\t1.2\tfoo\t1.2\n'
        self.assertEqual(package_pairs(raw),([('foo','1.2')],2))
    def test_bad_inventory(self):
        for raw in (b'',b'wrong',b'install ok half-configured\ta\t1\ta\t1\n',b'install ok installed\ta\t1\ta\tbad\n',b'install ok installed\ta\t1\ta\t1\n'*2):
            with self.subTest(raw=raw),self.assertRaises(ValueError):package_pairs(raw)
    def test_scan(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        with TemporaryDirectory() as d:
            root=Path(d); src=root/'inventory.json'; out=root/'audit.json'
            src.write_text(json.dumps(dict(ecosystem='Debian:13',binary_count=1,source_packages=1,raw_dpkg='install ok installed\tfoo\t1.2\tfoo\t1.2\n')))
            with patch(__name__+'.query',return_value=b'{"results":[{}]}') as q:
                self.assertEqual(audit(src,out),0)
                q.assert_called_once_with('Debian:13',[('foo','1.2')])
            self.assertTrue(json.loads(out.read_text())['scan_completed'])
            with patch(__name__+'.query',return_value=b'{"results":[{}]}'):
                self.assertEqual(audit(src,out),1)
            self.assertFalse(json.loads(out.read_text())['scan_completed'])
    def test_advisory_and_incomplete(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        for raw, verdict in ((b'{"results":[{"vulns":[{"id":"TEST-1"}]}]}','ADVISORIES_FOUND'),(b'{"results":[]}','INCOMPLETE')):
            with TemporaryDirectory() as d:
                root=Path(d); src=root/'inventory.json'; out=root/'audit.json'
                src.write_text(json.dumps(dict(ecosystem='Debian:13',binary_count=1,source_packages=1,raw_dpkg='install ok installed\tfoo\t1\tfoo\t1\n')))
                with patch(__name__+'.query',return_value=raw):self.assertEqual(audit(src,out),1)
                self.assertEqual(json.loads(out.read_text())['verdict'],verdict)


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--self-test',action='store_true'); p.add_argument('--capture',action='store_true'); p.add_argument('--inventory',type=Path); p.add_argument('--output',type=Path); a=p.parse_args()
    if a.self_test:unittest.main(argv=['debian_audit'],verbosity=2)
    if a.capture:
        print(json.dumps(capture(),sort_keys=True));raise SystemExit(0)
    if not a.inventory or not a.output:p.error('inventory and output required')
    raise SystemExit(audit(a.inventory,a.output))
