# V22 local forward research ledger (HOLD/DISABLED)

SQLite database in an owner-controlled private persistent directory. No database, licensed raw result payload or credential committed to Git. The CLI imports a sealed V6.2 BL1 ZIP with expected digest and creation clock, verifies the original archive, and freezes the first admitted forecast per native fixture. Duplicate or later same-fixture archives do not increase the count. Earlier out-of-order imports, changed kickoff/team identities and alias collisions reject the whole import. Use chronological archive imports; rescheduled fixtures require manual review, not automatic reassignment. SQLite write transactions and immutable-row triggers protect against ordinary application overwrites, not an administrator rewriting the database. The local creation timestamp is not externally attested.

```sh
python -m ops.v22_forward_ledger --db /private/ledger.sqlite register --archive sealed.zip --sha256 EXPECTED_SHA256 --created-utc 2026-11-26T03:00:00Z
python -m ops.v22_forward_ledger --db /private/ledger.sqlite settle --fixture-id NATIVE_ID --open-raw result.json --open-observed-utc 2026-11-29T20:00:00Z
python -m ops.v22_forward_ledger --db /private/ledger.sqlite report
```

The dates above are illustrative, not live evidence. To add dual raw settlement, additionally pass --fd-raw --fd-observed-utc --mapping --mapping-sha256 with independently reviewed mapping and authorized captures. Single and dual observations of one fixture count once; conflicting scores reject, rather than overwrite. Report re-audits archive and source semantics, but is not a V20 signature or trusted-clock verification. Verified credit stays zero. Back up the private DB and pin digests externally. No signed evidence automatically admitted. No recurring job or external storage is provisioned. Current research CI uploads an exact forecast ZIP and integrity/ledger reports with 14-day retention before later historical stages; runner DB is temporary. Owner must download/archive outside GitHub expiry for durable cross-run storage. No V21 raw-provider payload is included in that artifact. No authenticated 300-match cohort, EV or production deployment.
