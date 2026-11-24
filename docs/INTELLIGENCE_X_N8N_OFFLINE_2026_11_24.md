# Intelligence-X P5: n8n manual offline control-center pilot

Stacked on #588. Prior head c3eaf3697dd54f1940ca277d39cf35477ffa53e6:
five successful CI workflows; 2381 regression tests, 16 skipped, zero failures.
https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45387024800/job/138420493251

Deliverables:
- ops/intelligence_x_offline_batch.py: in-memory bounded batch of already loaded API response bytes,
  runs existing P3 normalizer, deduplicates exact URL/payload, counts rejects and emits only HOLD summary.
  No real P4 corroboration is run: P3 lacks authenticated upstream timestamps. No scheduling or I/O.
- research/intelligence_x/n8n_offline_demo.json: inactive three-node manual trigger, fixed synthetic
  report, fail-closed summary. No HTTP, command, webhook, schedule, credential, notification or GitHub write.
  The fixed fixture is NOT output from a live Python process; the integration boundary is not deployed.
  No arbitrary data forwarded; only fixed output fields. Alert is local output, not an external notification.
- Nine Python unittest methods; workflow structure test is not an n8n runtime/import test.

Official docs reviewed:
https://docs.n8n.io/workflows/export-import/
https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.manualworkflowtrigger/
https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.code/
n8n v2 uses publish/unpublish; a manual trigger is intentionally the only trigger.
Import the JSON into a private instance using the UI, keep unpublished, execute manually.
Expected synthetic output: total=2, candidates=1, rejected=1, alert=REJECTED_CAPTURE, status=HOLD.
Actual n8n instance, import and runtime execution not verified; no claim of 24/7 operation.
Before a real integration, require private hosting, version-pinned runtime and task runner,
authenticated bounded report transport from Python, rights, upstream clock/identity verification,
private retention controls, explicit cost approval and independent review. No production publishing.
Test: PYTHONPATH=ops python -m unittest discover -s ops/tests -p 'test_intelligence_x_offline_batch.py' -v
