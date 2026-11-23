# Main branch documentation-only CI trigger baseline probe (2026-11-23 HKT)

## Intent
This is deliberately a **documentation-only** Pull Request against `main`; it makes no code, workflow, source, model, betting, or credential changes.

## Reproducible acceptance
Before closing this probe, capture:
- Exact `main` base SHA `3a6bf4897baea419e1415748b57d2651ddf66da5`;
- Exact head SHA and one-file `docs/` change verified by GitHub;
- Which actual PR-triggered GitHub Actions workflows/jobs appear on this SHA, including the repository safety, offline prediction validation, ledger, `football-king-ci.yml`, and `football-king-regression.yml` workflows;
- Specifically compare existence or absence of `security-regression` and `failover-regression` with the proposed unmerged security fix in PR #467;
- Absence of a run is **not** equal to a failed run and **not** proof of active ruleset enforcement; report as `NOT_OBSERVED`.

After recording this evidence, close the Draft PR unmerged. Do not enable any model, source access, production recommendation or positive EV.
