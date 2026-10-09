# Screenshot evidence intake

Run: `python ops/screenshot_evidence_intake.py --image screenshot.png --manifest screenshot.json --output screenshot-audit.json`.

Manifest JSON contains `image_sha256` (SHA256 of actual image bytes), `fixture` (`event_id`, `league`, `home`, `away`), `screenshot` (`event_id`, `human_reviewed`, `observed_at_utc`, `home_goals`, `away_goals`, `minute`).

This is **not OCR**. It never reads text from pixels or validates the human-entered claims against the image; hash only ties a manifest to particular bytes. `human_reviewed` is self-attested. No provider identity is inferred or independent source evidence invented. The result is research-only and cannot authorize a betting recommendation. A real image understanding component and independently verified provider fixture mapping remain separate outstanding work.
