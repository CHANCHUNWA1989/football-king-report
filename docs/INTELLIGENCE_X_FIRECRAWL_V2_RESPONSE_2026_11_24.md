# Intelligence-X P3: Firecrawl v2 response contract, offline only

Reviewed 2026-11-24:
- https://docs.firecrawl.dev/api-reference/endpoint/scrape : POST https://api.firecrawl.dev/v2/scrape; documented success/data/markdown/metadata.sourceURL/metadata.url/metadata.statusCode. API-level and target-level statuses are distinct. Errors include credits, terms acceptance and throttling.
- https://www.firecrawl.dev/terms-of-service : revised 2026-10-07; service agreement and third-party provider terms are separate. Commercial use requires express authorization under the published terms. No project-specific rights established.
- https://www.firecrawl.dev/scrape : provider handles redirects. Equality of returned URLs is not proof of absence of intermediate redirects.

This stacked draft depends on #585. Only already captured synthetic response bytes are tested. No live requests, account creation, secret reading, retries, background collection or purchase. The normalizer conservatively requires both documented URL fields to equal the reviewed request URL, no warnings/errors, target/API 200, bounded UTF-8 JSON and nonempty markdown. Duplicate JSON keys and non-finite constants are refused. The hash binds API response bytes, not original publisher bytes. Local collection time is never publisher time. Extra metadata claims cannot promote eligibility.

## Real pilot acceptance
- Confirm actual account terms, target publisher authorization, scopes (research, retention, model use), source ownership and independent evidence privately. See #551/#554.
- Independently verify actual response schema on an authorized test page; exact API destination, no credential forwarding, network/redirect and DNS controls must be established before transport code.
- Establish quota budget and explicit opt-in for paid use; do not infer cache freshness from arrival time.
- Retain private original evidence, clock provenance, independent publisher corroboration and fixture IDs.
- Keep HOLD / DISABLED; no actual source or model approval is created.

Test: PYTHONPATH=ops python -m unittest discover -s ops/tests -p 'test_intelligence_x_firecrawl_v2_response.py' -v
