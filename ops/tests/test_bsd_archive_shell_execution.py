"""Execute the proposed BSD archive Bash against an actual LOCAL bare Git remote.

No GitHub token, Internet or provider calls. The same Bash that runs in
GitHub Actions is exercised with real Git history, one-commit multi-file
writes, stale replay, branch absence, and non-fast-forward concurrency.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bsd_free import collect

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = "archive/bsd-free-research-v1"
REAL_GIT = shutil.which("git")
if REAL_GIT is None:
    raise RuntimeError("LOCAL_GIT_REQUIRED")


def git(*args, cwd=None, check=True, input=None):
    return subprocess.run(
        [REAL_GIT, *map(str, args)], cwd=cwd, input=input, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check,
        timeout=15,
    )


def archive_script():
    workflow = (ROOT / ".github/workflows/football-king-bsd-free.yml").read_text(
        encoding="utf-8")
    marker = "      - name: Atomically commit BSD research files to archive branch\n"
    if workflow.count(marker) != 1:
        raise ValueError("BSD_ATOMIC_ARCHIVER_STEP_NOT_UNIQUE")
    tail = workflow.split(marker, 1)[1].split("\n  report_failure:\n", 1)[0]
    if tail.count("        run: |\n") != 1:
        raise ValueError("BSD_ATOMIC_ARCHIVER_RUN_BLOCK_NOT_UNIQUE")
    body = tail.split("        run: |\n", 1)[1]
    if not body.startswith("          set -euo pipefail"):
        raise ValueError("BSD_ATOMIC_ARCHIVER_SHELL_CHANGED")
    if "\n      - name:" in body:
        raise ValueError("BSD_ATOMIC_ARCHIVER_ADDED_STEP_UNEXPECTED")
    return textwrap.dedent(body)


def research_doc(*, minutes_ago=0):
    now = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    doc = collect(now=now, token="")
    doc.update({
        "status": "RESEARCH_ONLY", "key_present": True,
        "requests_attempted": 3, "league_count": 1,
        "fixture_count": 1, "market_count": 1,
        "events": [{
            "league": "bundesliga", "source_event_id": "fixture-1",
            "home": "Bayern Munich", "away": "Dortmund",
            "kickoff_utc": (now + timedelta(days=2)).isoformat(),
            "market_last_update_utc": (now - timedelta(minutes=20)).isoformat(),
            "oldest_leg_update_utc": (now - timedelta(minutes=20)).isoformat(),
            "p_home": .62, "p_draw": .22, "p_away": .16,
            "market_source": "BSD_FREE_CONSENSUS_ONLY",
            "raw_prices_published": False, "not_executable_odds": True,
        }],
    })
    return doc


class LocalBareArchive:
    def __init__(self, tmp, *, existing=None):
        self.root = Path(tmp)
        self.origin = self.root / "origin.git"
        self.writer = self.root / "bsd-write-archive"
        self.seed = self.root / "seed"
        self.t = self.root / "runner-temp"
        self.t.mkdir()
        git("init", "--bare", "-q", self.origin)
        git("init", "-q", self.seed)
        git("-C", self.seed, "config", "user.name", "Local archive fixture")
        git("-C", self.seed, "config", "user.email", "fixture@example.invalid")
        git("-C", self.seed, "checkout", "-qb", ARCHIVE)
        for path, contents in (existing or {}).items():
            output = self.seed / path
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(contents)
        git("-C", self.seed, "add", "-A")
        git("-C", self.seed, "commit", "-qm", "Local data-only fixture", "--allow-empty")
        git("-C", self.seed, "remote", "add", "origin", self.origin)
        git("-C", self.seed, "push", "-q", "origin", f"HEAD:refs/heads/{ARCHIVE}")
        git("clone", "-q", "--branch", ARCHIVE, self.origin, self.writer)
        # Match actions/checkout's non-cone data-only sparse checkout, not
        # a convenient full clone that might hide staging regressions.
        git("-C", self.writer, "sparse-checkout", "init", "--no-cone")
        git("-C", self.writer, "sparse-checkout", "set",
            "sources/bsd_history", "sources/bsd_status_latest.json",
            "sources/bsd_market_latest.json")
        (self.root / "ops").symlink_to(ROOT / "ops", target_is_directory=True)
        (self.root / "bsd").mkdir()
        self.pre = self.head()

    def head(self):
        return git("--git-dir", self.origin, "rev-parse",
                   f"refs/heads/{ARCHIVE}").stdout.strip()

    def read(self, path):
        r = git("--git-dir", self.origin, "show",
                f"refs/heads/{ARCHIVE}:{path}", check=False)
        if r.returncode:
            return None
        return r.stdout.encode("utf-8")

    def commit_paths(self):
        return set(git("--git-dir", self.origin, "diff-tree", "--no-commit-id",
                       "--name-only", "-r", self.head()).stdout.splitlines())

    def run(self, document, *, run_id="88800000", attempt="1", extra_env=None):
        (self.root / "bsd" / "bsd-result.json").write_text(
            json.dumps(document, ensure_ascii=False), encoding="utf-8")
        env = dict(os.environ,
                   BSD_ARCHIVE_REF=ARCHIVE, RUNNER_TEMP=str(self.t),
                   GITHUB_RUN_ID=run_id, GITHUB_RUN_ATTEMPT=attempt)
        for key in ("GH_TOKEN", "GITHUB_TOKEN", "BSD_FREE_API_TOKEN"):
            env.pop(key, None)
        env.update(extra_env or {})
        return subprocess.run(
            ["bash", "-c", archive_script()], cwd=self.root,
            env=env, capture_output=True, text=True, timeout=35,
            check=False,
        )

    def remove_branch(self):
        git("--git-dir", self.origin, "update-ref", "-d",
            f"refs/heads/{ARCHIVE}")


# Only for the concurrency fixture: intercept FIRST push, create a competing
# commit with a newer status, and let original non-force push be rejected.
GIT_WRAPPER = r'''#!/usr/bin/env python3
import os,sys,subprocess
from pathlib import Path
real=os.environ["BSD_TEST_REAL_GIT"]
args=sys.argv[1:]
mark=Path(os.environ["BSD_TEST_INJECTION_MARK"])
if "push" in args and not mark.exists():
    mark.write_text("injected")
    peer=os.environ["BSD_TEST_PEER"]
    source=Path(os.environ["BSD_TEST_CONCURRENT_DOC"])
    dest=Path(peer)/"sources"/"bsd_status_latest.json"
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes(source.read_bytes())
    def run(*argv):
        subprocess.run([real,"-C",peer,*argv],check=True,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    run("add","sources/bsd_status_latest.json")
    run("commit","-m","Concurrent actor new archive status")
    run("push","origin","HEAD:refs/heads/archive/bsd-free-research-v1")
os.execv(real,[real,*args])
'''


class BSDArchiveAtomicGitExecutionTests(unittest.TestCase):
    def test_noneligible_history_and_status_share_one_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = LocalBareArchive(tmp)
            result = h.run(collect(now=datetime.now(timezone.utc), token=""))
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertNotEqual(h.pre, h.head())
            changes = h.commit_paths()
            self.assertEqual(len(changes), 2)
            self.assertIn("sources/bsd_status_latest.json", changes)
            self.assertTrue(any(p.startswith("sources/bsd_history/") for p in changes))
            self.assertNotIn("sources/bsd_market_latest.json", changes)
            self.assertEqual(json.loads(h.read("sources/bsd_status_latest.json"))[
                "production_recommendations"], "DISABLED")

    def test_qualified_history_status_and_market_are_one_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = LocalBareArchive(tmp)
            doc = research_doc()
            result = h.run(doc)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            changes = h.commit_paths()
            self.assertEqual(len(changes), 3, changes)
            self.assertTrue(any(p.startswith("sources/bsd_history/") for p in changes))
            self.assertIn("sources/bsd_status_latest.json", changes)
            self.assertIn("sources/bsd_market_latest.json", changes)
            self.assertEqual(h.read("sources/bsd_status_latest.json"),
                             h.read("sources/bsd_market_latest.json"))
            self.assertEqual(json.loads(h.read("sources/bsd_market_latest.json"))[
                "production_recommendations"], "DISABLED")
            self.assertEqual(git("--git-dir", h.origin, "rev-list", "--count",
                                 h.head()).stdout.strip(), "2")

    def test_older_status_replay_writes_only_history_and_preserves_latest(self):
        with tempfile.TemporaryDirectory() as tmp:
            newer = collect(now=datetime.now(timezone.utc), token="")
            old = collect(now=datetime.now(timezone.utc) -
                          timedelta(minutes=30), token="")
            original = json.dumps(newer).encode()
            h = LocalBareArchive(tmp, existing={
                "sources/bsd_status_latest.json": original})
            r = h.run(old)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertEqual(h.read("sources/bsd_status_latest.json"), original)
            self.assertEqual(len(h.commit_paths()), 1)
            self.assertTrue(next(iter(h.commit_paths())).startswith(
                "sources/bsd_history/"))

    def test_stale_eligible_replay_never_overwrites_market(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = research_doc(minutes_ago=40)
            newer = research_doc()
            previous = research_doc(minutes_ago=80)
            status = json.dumps(newer).encode()
            market = json.dumps(previous).encode()
            h = LocalBareArchive(tmp, existing={
                "sources/bsd_status_latest.json": status,
                "sources/bsd_market_latest.json": market,
            })
            r = h.run(old)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertEqual(h.read("sources/bsd_status_latest.json"), status)
            self.assertEqual(h.read("sources/bsd_market_latest.json"), market)
            self.assertEqual(len(h.commit_paths()), 1)

    def test_equal_timestamp_conflict_does_not_update_archive_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = collect(now=datetime.now(timezone.utc), token="")
            conflicting = dict(doc)
            conflicting["status"] = "NO_COMPARABLE_MARKET"
            h = LocalBareArchive(tmp, existing={
                "sources/bsd_status_latest.json": json.dumps(conflicting).encode()})
            r = h.run(doc)
            self.assertNotEqual(r.returncode, 0)
            self.assertEqual(h.head(), h.pre)

    def test_missing_archive_branch_refuses_no_main_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = LocalBareArchive(tmp)
            h.remove_branch()
            r = h.run(collect(now=datetime.now(timezone.utc), token=""))
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("fatal:", r.stderr.lower())
            self.assertNotEqual(git("--git-dir", h.origin, "show-ref", "--verify",
                                    f"refs/heads/{ARCHIVE}", check=False).returncode,
                                0)

    def test_replay_same_run_id_same_bytes_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = LocalBareArchive(tmp)
            doc = collect(now=datetime.now(timezone.utc), token="")
            first = h.run(doc)
            self.assertEqual(first.returncode, 0, first.stderr)
            new_head = h.head()
            second = h.run(doc)
            self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
            self.assertEqual(h.head(), new_head)
            self.assertIn("BSD_ARCHIVE_IDEMPOTENT_NO_CHANGES", second.stdout)

    def test_local_non_fast_forward_competitor_causes_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = LocalBareArchive(tmp)
            peer = h.root / "peer"
            git("clone", "-q", "--branch", ARCHIVE, h.origin, peer)
            git("-C", peer, "config", "user.name", "Competing actor")
            git("-C", peer, "config", "user.email", "other@example.invalid")
            newer = collect(now=datetime.now(timezone.utc), token="")
            stale = collect(now=datetime.now(timezone.utc) -
                            timedelta(minutes=30), token="")
            newer_file = h.root / "new-status.json"
            newer_file.write_text(json.dumps(newer), encoding="utf-8")
            bin_dir = h.root / "fake-bin"
            bin_dir.mkdir()
            wrapper = bin_dir / "git"
            wrapper.write_text(GIT_WRAPPER, encoding="utf-8")
            wrapper.chmod(0o755)
            injected = h.root / "injected"
            env = {
                "PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
                "BSD_TEST_REAL_GIT": REAL_GIT,
                "BSD_TEST_INJECTION_MARK": str(injected),
                "BSD_TEST_PEER": str(peer),
                "BSD_TEST_CONCURRENT_DOC": str(newer_file),
            }
            r = h.run(stale, extra_env=env)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertTrue(injected.exists())
            self.assertIn("BSD_ARCHIVE_CONCURRENT_UPDATE_RETRY=1", r.stdout)
            self.assertEqual(h.read("sources/bsd_status_latest.json"),
                             newer_file.read_bytes())
            self.assertEqual(len(h.commit_paths()), 1)
            self.assertNotIn("sources/bsd_market_latest.json", h.commit_paths())

    def test_archive_script_never_pushes_to_main_or_forces(self):
        script = archive_script()
        self.assertIn('test "$BSD_ARCHIVE_REF" = "archive/bsd-free-research-v1"',
                      script)
        self.assertIn('push origin "HEAD:refs/heads/$BSD_ARCHIVE_REF"', script)
        self.assertIn('git -C "$archive_dir" commit', script)
        self.assertIn('git -C "$archive_dir" fetch', script)
        self.assertNotIn("refs/heads/main", script)
        self.assertNotIn("--force", script)
        self.assertNotIn("gh api -X PUT", script)


    def test_mutable_archive_history_symlink_refuses_unsafe_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = LocalBareArchive(tmp)
            out = h.root / "not-in-repo"
            out.mkdir()
            source_dir = h.seed / "sources"
            source_dir.mkdir(exist_ok=True)
            (source_dir / "bsd_history").symlink_to(
                out, target_is_directory=True)
            git("-C", h.seed, "add", "--", "sources/bsd_history")
            git("-C", h.seed, "commit", "-qm", "Adversarial history symlink")
            git("-C", h.seed, "push", "-q", "origin",
                f"HEAD:refs/heads/{ARCHIVE}")
            expected = h.head()
            result = h.run(collect(now=datetime.now(timezone.utc), token=""))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("BSD_ARCHIVE_HISTORY_PATH_UNSAFE", result.stdout)
            self.assertEqual(h.head(), expected)
            self.assertEqual(list(out.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
