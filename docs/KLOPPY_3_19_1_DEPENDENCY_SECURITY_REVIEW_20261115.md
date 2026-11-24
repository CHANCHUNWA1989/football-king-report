# Kloppy 3.19.1 — Third-party package security review (2026-11-15)

**Status: RESEARCH_ONLY; HOLD / production_recommendations=DISABLED.**
Scope: immutable, version/hash-pinned **17-wheel** VNext research lock for
**CPython 3.11 / Linux x86_64 only**, not deployment or model certification.

## Real assessment performed

An external isolated Python 3.11 Linux research sandbox retrieved the exact
17 public Python wheels specified in
[`ops/research_locks/kloppy-3.19.1-cp311-linux-x86_64.txt`](../ops/research_locks/kloppy-3.19.1-cp311-linux-x86_64.txt)
with `pip download --only-binary=:all: --require-hashes`, confirming
**all downloaded SHA-256 hashes** match the checked-in lock.

The checked-in lock was retrieved from GitHub PR #470 commit
`dac2b1b6b71b9e0d745d1150361c71dfd0ca5be5`, verified against
Git blob SHA-1 `eb020ea501dbfdc714e7eae6a04b6af4aee1abff`.

Using `pip-audit 2.10.1`, two separate online vulnerability-service
queries completed with **exit status 0** on 2026-11-15 (UTC):

| Advisory service | Locked packages returned | Known vulnerability records reported | JSON SHA-256 | Result |
| --- | ---: | ---: | --- | --- |
| [PyPI advisory database](https://pypi.org/) (`--vulnerability-service pypi`) | 17/17 | **0** | `b2cbc80400c2b0f2fabe08594e0984f253f813d1393c891a80f39a7e554fded7` | No known vulnerabilities reported |
| [OSV](https://osv.dev/) (`--vulnerability-service osv`) | 17/17 | **0** | `b2cbc80400c2b0f2fabe08594e0984f253f813d1393c891a80f39a7e554fded7` | No known vulnerabilities reported |

The two JSON files are identically shaped because the audited versions and
vulnerability lists were identical. Both queries were actually executed
separately; their package/version coverage was inspected after parsing each
JSON. A zero-result advisory query is *not* proof of no undisclosed
vulnerabilities, malicious code, correct maintainer identity or safe use of
data. This is a dated research snapshot, **not a continuously updated
security assurance**. Scan receipts remain external to the repository; these
hashes let an independent reviewer compare copies if subsequently supplied.

A `pip-audit --format cyclonedx-json` export confirmed **17 components**,
CycloneDX 1.4, and zero reported vulnerability entries. The SBOM was not
treated as a signed upstream software attestation.

## Actual wheel license evidence

The license declarations below were read from each **downloaded wheel's
`*.dist-info/METADATA`**; the same ZIPs were inspected for embedded
license-related files. **17/17 contain at least one embedded LICENSE-like
file**. These labels are package-authored metadata claims, not independent
legal due diligence.

| Package | Locked version | Wheel license declaration |
| --- | --- | --- |
| aiohappyeyeballs | 2.7.1 | PSF-2.0 (legacy field / classifier) |
| aiohttp | 3.14.5 | Apache-2.0 AND MIT (SPDX expression) |
| aiosignal | 1.4.0 | Apache 2.0 (legacy field) |
| attrs | 26.1.0 | MIT |
| frozenlist | 1.8.0 | Apache-2.0 |
| fsspec | 2026.9.0 | BSD-3-Clause |
| idna | 3.20 | BSD-3-Clause |
| kloppy | 3.19.1 | BSD-3-Clause (legacy license text and classifier) |
| lxml | 6.1.3 | BSD-3-Clause (package metadata; bundled LICENSES.txt also exists) |
| multidict | 7.2.1 | Apache-2.0 |
| propcache | 0.5.4 | Apache-2.0 (NOTICE also present) |
| python-dateutil | 4.0.0 | BSD-3-Clause |
| pytz | 2026.6 | MIT |
| sortedcontainers | 2.4.0 | Apache 2.0 |
| typing_extensions | 4.16.0 | PSF-2.0 |
| tzdata | 2026.6 | Apache-2.0 |
| yarl | 1.25.1 | Apache-2.0 (NOTICE also present) |

**Additional legal review required:** `aiohttp` wheel contains additional
`dist-info/licenses/vendor/llhttp/LICENSE` content; `lxml` includes
additional `LICENSES.txt`. A later legal review must inspect those
third-party notices and all licensing obligations in context before
distributing or deploying. The presence of a license document does **not**
grant rights to upstream match/tracking data.

## Repeatable, fail-closed scan workflow (isolated research only)

```sh
# Use the same pre-reviewed 17-wheel lock. pip-audit is a separate
# inspection-tool dependency and was v2.10.1 on the observed run.
python -m pip_audit --disable-pip --no-deps --progress-spinner off \
  --timeout 30 -s pypi \
  -r ops/research_locks/kloppy-3.19.1-cp311-linux-x86_64.txt \
  -f json -o /private/pypi-audit.json

python -m pip_audit --disable-pip --no-deps --progress-spinner off \
  --timeout 30 -s osv \
  -r ops/research_locks/kloppy-3.19.1-cp311-linux-x86_64.txt \
  -f json -o /private/osv-audit.json

# Review every package/version, not only summary counts.
python -m ops.kloppy_research_vulnerability_gate \
  --lock ops/research_locks/kloppy-3.19.1-cp311-linux-x86_64.txt \
  --pypi-json /private/pypi-audit.json \
  --osv-json /private/osv-audit.json
```

The new standard-library-only gate checks **both local result JSONs**
against the exact lock, rejects missing, extra, duplicated or mismatched
package versions, malformed/missing vulnerability lists and any
reported vulnerability. It was run against both *actual* 17-package scan
files from this exercise and returned:
`RESEARCH_ONLY_REPORTS_NO_KNOWN_VULNS`,
`reported_known_vulnerability_count: {"pypi":0,"osv":0}`.
The gate has **9 standalone synthetic negative/positive tests**, including
a reported vulnerability and partial advisory feed. This contract is tested
in GitHub CI without downloading packages or contacting public databases.

**Trust boundary:** The JSON inputs have no cryptographic source signature
or trustworthy timestamp. Passing this local parser does NOT independently
prove scans were performed, are fresh or came from the claimed providers.
The gate's own output always sets
`scan_source_authenticity_verified=false`,
`scan_freshness_independently_verified=false`,
`all_transitive_licenses_legally_cleared=false` and
`production_recommendations=DISABLED`.

## Remaining blockers

1. Independent reviewer to confirm actual wheel-source provenance and
   dependency licenses, including vendored notices, rather than relying on
   package METADATA.
2. Repeat advisory scan near any later release/merge/deployment because
   vulnerabilities may be published after this 2026-11-15 snapshot.
3. No authorized provider event/tracking feed is supplied; third-party
   **data licenses** are separate from these Python package licenses.
4. Main branch is not protected; independent code review and governance
   prerequisite is [Issue #439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439).
5. No independently certified forward samples, tested predictive edge,
   verified executable betting prices or positive EV.

**Keep Draft PR #470 open and unmerged; HOLD/DISABLED.**
