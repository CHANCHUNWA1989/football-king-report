"""Observed live, anonymous Agent Reach GitHub-only smoke test.

Runs ONLY a fixed public repo read via the pinned Agent Reach CLI. The successful
result remains QUARANTINE / HOLD; this is not source authentication or a wager.
The process receives an empty HOME and an explicit minimal environment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from agent_reach_native_github import canonical_repo, convert_native
from agent_reach_quarantine import Rejected

UPSTREAM_RELEASE_SHA = "7a38047acf26a729cbb27851e3cb81639da86b29"
UPSTREAM_VERSION = "1.6.1"
MAX_OUTPUT_BYTES = 200_000
REPO_ALLOWLIST = frozenset({"Panniantong/Agent-Reach"})
EXPECTED_CHANNEL = ("agent-reach", "github", "read", "Panniantong/Agent-Reach",
                    "--backend", "github-api", "--timeout", "15")


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def minimal_environment(home: str, path: str) -> dict[str, str]:
    """Do not inherit GitHub token, home, proxy, cloud credentials or login."""
    return {
        "HOME": home,
        "PATH": path,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
        "LANG": "C.UTF-8",
    }


def smoke(*, repo: str, vendor_dir: Path, output_path: Path,
          runner=subprocess.run, clock=timestamp) -> tuple[dict, int]:
    """Return sanitized receipt and 0 on success; HOLD and 2 on any failure."""
    receipt = {
        "schema": "agent-reach-public-github-smoke-v1",
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "repo": None,
        "upstream_expected_sha": UPSTREAM_RELEASE_SHA,
        "upstream_version_expected": UPSTREAM_VERSION,
        "observed_native_schema": None,
        "agent_reach_executed": False,
        "agent_reach_execution_independently_verified": False,
        "capture_status": "NOT_ATTEMPTED",
        "reason": "UNVERIFIED_LIVE_COLLECTION",
        "source_authorized": False,
        "eligible_for_model": False,
        "verified_market_odds": False,
        "verified_positive_ev": None,
        "network_requests": None,
        "runner_clock_independently_attested": False,
        "raw_text_retained": False,
    }
    try:
        repo = canonical_repo(repo)
        if repo not in REPO_ALLOWLIST:
            raise Rejected("REPO_NOT_ALLOWED")
        receipt["repo"] = repo
        # Ensure exact upstream source bytes were checked out, not a moving tag.
        git = runner(["git", "-C", str(vendor_dir), "rev-parse", "HEAD"],
                     capture_output=True, text=True, timeout=10)
        if git.returncode != 0 or git.stdout.strip() != UPSTREAM_RELEASE_SHA:
            raise Rejected("UPSTREAM_SHA_MISMATCH")
        receipt["source_commit_verified_locally"] = True
        with tempfile.TemporaryDirectory(prefix="agent-reach-no-login-") as home:
            env = minimal_environment(home, os.environ.get("PATH", ""))
            ver = runner(["agent-reach", "version"], capture_output=True,
                         text=True, timeout=20, env=env)
            if ver.returncode != 0 or len(ver.stdout.encode("utf-8")) > 20000:
                raise Rejected("VERSION_COMMAND_FAILED")
            ver_json = json.loads(ver.stdout)
            if (not isinstance(ver_json, dict) or ver_json.get("ok") is not True
                    or (ver_json.get("result") or {}).get("version") != UPSTREAM_VERSION):
                raise Rejected("CLI_VERSION_MISMATCH")
            receipt["cli_version_verified_locally"] = True
            receipt["cli_start_utc_runner"] = clock()
            # No --setup, --login, --update, search, or dynamic user arguments.
            # The backend is explicitly github-api (no gh token/no browser).
            receipt["agent_reach_executed"] = True  # attempted, not proof of usable data
            call = runner(list(EXPECTED_CHANNEL), capture_output=True, text=True,
                          timeout=30, env=env)
            receipt["cli_end_utc_runner"] = clock()
            receipt["cli_exit_code"] = call.returncode
            if call.returncode != 0:
                raise Rejected("CLI_EXIT_NONZERO")
            raw = call.stdout.encode("utf-8")
            if not raw or len(raw) > MAX_OUTPUT_BYTES:
                raise Rejected("NATIVE_OUTPUT_SIZE_INVALID")
            native = json.loads(raw)
            # v1.6 JSON output; mismatches or postulated site data fail closed.
            imported = convert_native(
                native, repo=repo,
                captured_utc=receipt["cli_end_utc_runner"],
                now_utc=receipt["cli_end_utc_runner"],
            )
            receipt.update({
                "capture_status": "PUBLIC_READ_OBSERVED_UNATTESTED",
                "reason": "LIVE_PUBLIC_READ_NOT_SPORTS_EVIDENCE",
                "native_output_sha256_local": hashlib.sha256(raw).hexdigest(),
                "observed_native_schema": imported["agent_reach_native_schema_version"],
                "data_status": imported["records"][0]["status"],
                "published_utc_independently_verified": False,
                "source_url": imported["records"][0]["source_url"],
                "source_content_sha256_local": imported["records"][0]["content_sha256_local_only"],
                "agent_reach_execution_independently_verified": False,
            })
            return receipt, 0
    except (Rejected, OSError, subprocess.TimeoutExpired, ValueError, TypeError,
            UnicodeError, json.JSONDecodeError) as exc:
        # No error string: stderr/path/token/body can all be untrusted or sensitive.
        reason = str(exc) if isinstance(exc, Rejected) else type(exc).__name__
        receipt["capture_status"] = "HOLD"
        receipt["reason"] = reason[:64]
        return receipt, 2


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", required=True)
    p.add_argument("--vendor-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        if args.output.is_symlink() or args.output.resolve().is_relative_to(Path.cwd()):
            p.error("receipt must be written outside repository working directory")
    except OSError:
        p.error("unsafe output path")
    receipt, code = smoke(repo=args.repo, vendor_dir=args.vendor_dir,
                          output_path=args.output)
    args.output.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"agent_reach_capture_status={receipt['capture_status']}; formal_betting=DISABLED")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
