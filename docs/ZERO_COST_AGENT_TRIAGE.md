# Zero-cost Agent triage (safe first stage)

This optional workflow reads existing repository snapshots, runs the current shadow audit, and produces a sanitized JSON queue for ChatGPT Work/Codex to review. It **does not automatically invoke Codex**, create fixes, open PRs, consume OpenAI API tokens, place bets, or merge anything. No additional bookmaker API calls. Production stays DISABLED/HOLD.

- Runs once daily on standard GitHub Actions runners, plus manual dispatch.
- Requires only read permissions, bounded runtime, 7-day artifact retention.
- On an invalid, unexpectedly READY, or unsafe audit, fails closed rather than guessing.
- Use the generated `football-king-agent-triage` artifact in Work to select a small issue, reproduce it, run tests and request a **draft PR**. Never pass Secrets to prompts.
- No zero-cost guarantee for all future Codex usage; verify included account quotas before enabling unattended AI calls. Public repository standard GitHub-hosted Actions jobs are generally free subject to policy and storage constraints.
- Existing `football-king-agent-audit.yml` remains unchanged; this is a standalone draft PR until review.

Manual verification:
```bash
python -m unittest discover -s ops/tests -p test_agent_zero_cost_triage.py -v
python ops/agent_orchestrator.py --output agent-audit.json || test "$?" -eq 2
python ops/agent_zero_cost_triage.py --input agent-audit.json --output agent-triage.json
```
