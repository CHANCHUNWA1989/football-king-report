import base64, hashlib, json, re, subprocess, sys
from importlib.metadata import distribution
from pathlib import Path


def verify_file(root, path, mode, expected, size):
    path = path.resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('file outside runtime prefix or not regular')
    if mode not in ('sha256', 'sha384', 'sha512') or type(size) is not int or size < 0:
        raise ValueError('unsupported RECORD metadata')
    h = hashlib.new(mode)
    count = 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
            count += len(block)
    if count != size or base64.urlsafe_b64encode(h.digest()).decode().rstrip('=') != expected:
        raise ValueError('installed file differs from RECORD')


def audit():
    root = Path(sys.prefix).resolve()
    names = []
    for line in subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True).splitlines():
        match = re.fullmatch(r'([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)', line)
        if not match:
            raise ValueError('unexpected package declaration')
        names.append(match[1])
    if len(names) != 23:
        raise ValueError('unexpected package count')
    counts = {}
    skipped = 0
    for name in sorted(names):
        dist = distribution(name)
        files = dist.files
        if not files:
            raise ValueError('missing RECORD inventory')
        verified = 0
        for entry in files:
            if entry.hash is None:
                if not (entry.name == 'RECORD' and entry.parent.name.endswith('.dist-info') or entry.suffix == '.pyc' and entry.parent.name == '__pycache__'):
                    raise ValueError('unexpected unhashed entry')
                skipped += 1
                continue
            verify_file(root, Path(dist.locate_file(entry)), entry.hash.mode, entry.hash.value, entry.size)
            verified += 1
        if not verified:
            raise ValueError('empty hashed inventory')
        counts[name] = verified
    return dict(schema='scrapling-installed-record-v1', packages=len(counts), files_verified=sum(counts.values()), counts=counts, unhashed_record_or_pyc=skipped, installed_record_consistency=True, wheel_hash_verified=False, vulnerability_scan_completed=False, status='HOLD', model_input_allowed=False, live_trading='DISABLED', production_recommendations='DISABLED')

if __name__ == '__main__':
    print(json.dumps(audit(), sort_keys=True))
