"""Regression tests for mandatory GitHub Actions check identities.

Only reads two versioned workflow files; never fetches data or changes the
repository. A required job must be emitted on every PR and have a unique ID.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ".github/workflows/football-king-ci.yml"
FAILOVER = ".github/workflows/football-king-regression.yml"
EXPECTED = {CORE: "security-regression", FAILOVER: "failover-regression"}


def _jobs(text):
    match = re.search(r"(?m)^jobs:\s*$", text)
    if match is None:
        raise ValueError("NO_WORKFLOW_JOBS")
    tail = text[match.end():]
    names = re.findall(r"(?m)^  ([a-z][a-z0-9_-]*):\s*$", tail)
    if not names or len(names) != len(set(names)):
        raise ValueError("MISSING_OR_DUPLICATE_JOB_ID")
    return names


def _unfiltered_pull_request(text):
    lines = text.splitlines()
    if not any(line.strip() == "on:" and line == "on:" for line in lines):
        raise ValueError("NO_WORKFLOW_EVENT_BLOCK")
    try:
        start = lines.index("  pull_request:")
    except ValueError:
        raise ValueError("PR_TRIGGER_MISSING") from None
    for line in lines[start + 1:]:
        # Any sibling event or new top-level section ends this event.
        if line and not line.startswith(" ") and not line.startswith("#"):
            break
        if re.match(r"^  [a-zA-Z_][a-zA-Z0-9_-]*:", line):
            break
        if line.strip() and not line.lstrip().startswith("#"):
            raise ValueError("PR_TRIGGER_FILTERED_OR_UNSUPPORTED")
    return True


def _credentials_not_persisted(text):
    """No PR-tested checkout may leave the workflow token in git config."""
    lines = text.splitlines()
    checkout = [
        i for i, line in enumerate(lines)
        if re.match(r"^ {6,8}-? ?uses: actions/checkout@", line)
    ]
    if not checkout:
        raise ValueError("CHECKOUT_STEP_MISSING")
    for start in checkout:
        end = next((i for i in range(start + 1, len(lines))
                    if re.match(r"^      - ", lines[i])
                    or re.match(r"^  [a-z][a-z0-9_-]*:", lines[i])),
                   len(lines))
        # The checkout step's with: must explicitly disable persistence.
        # A false value in a later step must never count.
        section = lines[start + 1:end]
        if ("        with:" not in section
                or "          persist-credentials: false" not in section):
            raise ValueError("PERSISTED_CHECKOUT_CREDENTIALS")
    return True



def _non_skippable_required_job(text, job_name):
    """Refuse if/continue-on-error bypass on a mandatory CI job or test step.

    Deliberately strict: if a future required check needs conditional execution,
    it must receive independent review rather than silently turn green.
    """
    match = re.search(r"(?m)^  " + re.escape(job_name) + r":\s*$", text)
    if match is None:
        raise ValueError("REQUIRED_JOB_ID_MISSING: " + job_name)
    tail = text[match.end():]
    next_job_or_section = re.search(
        r"(?m)^(?:  [a-z][a-z0-9_-]*:|[a-z][a-z0-9_-]*:)\s*$", tail)
    section = tail[:next_job_or_section.start()] if next_job_or_section else tail
    if re.search(r"(?m)^\s+(?:if|continue-on-error):", section):
        raise ValueError("CONDITIONAL_OR_IGNORED_REQUIRED_CHECK: " + job_name)
    return True



def _no_privileged_events_or_token_grants(text):
    """Only safe PR/push/manual events, read-only tokens and immutable actions.

    These static checks are additional negative tests, not a substitute for
    GitHub's effective rulesets, independent review or workflow execution.
    """
    lines = text.splitlines()
    try:
        on_index = lines.index("on:")
    except ValueError:
        raise ValueError("NO_WORKFLOW_EVENT_BLOCK") from None
    allowed_events = {"pull_request", "push", "workflow_dispatch"}
    events = []
    for line in lines[on_index + 1:]:
        if line and not line.startswith((" ", "#")):
            break
        event = re.match(r"^  ([a-z][a-z0-9_-]*):", line)
        if event is not None:
            events.append(event.group(1))
    if (len(events) != len(set(events))
            or not events or not set(events).issubset(allowed_events)):
        raise ValueError("UNSAFE_WORKFLOW_EVENT")

    # Top-level and job-level permissions must be explicit, non-duplicated,
    # and limited to contents: read. GitHub grants default job permissions
    # from workflow permissions unless a job overrides them.
    blocks = []
    for i, line in enumerate(lines):
        if re.match(r"^\s*permissions:", line):
            indent = len(line) - len(line.lstrip(" "))
            if indent not in (0, 4) or line != " " * indent + "permissions:":
                raise ValueError("UNSAFE_TOKEN_PERMISSIONS")
            props = []
            for child in lines[i + 1:]:
                if not child.strip() or child.lstrip().startswith("#"):
                    continue
                depth = len(child) - len(child.lstrip(" "))
                if depth <= indent:
                    break
                if depth != indent + 2:
                    raise ValueError("UNSAFE_TOKEN_PERMISSIONS")
                props.append(child.strip())
            if props != ["contents: read"]:
                raise ValueError("UNSAFE_TOKEN_PERMISSIONS")
            blocks.append(indent)
    if blocks.count(0) != 1:
        raise ValueError("UNSAFE_TOKEN_PERMISSIONS")

    if re.search(r"\$\{\{[^}]*\b(?:secrets|github\.token)\b", text, re.I):
        raise ValueError("UNSAFE_TOKEN_REFERENCE")

    # Both GitHub Actions step shapes are valid: "- uses: owner/action@sha"
    # and "- name: ..." followed by an indented "uses: ...".
    uses = [line for line in lines
            if re.match(r"^\s+(?:-\s+)?uses:", line)]
    if not uses:
        raise ValueError("MUTABLE_ACTION_REFERENCE")
    for line in uses:
        if not re.fullmatch(
                r"\s+(?:-\s+)?uses:\s+[A-Za-z0-9_./-]+@[0-9a-f]{40}\s*",
                line):
            raise ValueError("MUTABLE_ACTION_REFERENCE")
    return True


def validate(sources):
    if set(sources) != set(EXPECTED):
        raise ValueError("REQUIRED_WORKFLOW_MISSING")
    seen = set()
    for path, expected in EXPECTED.items():
        source = sources[path]
        _unfiltered_pull_request(source)
        _no_privileged_events_or_token_grants(source)
        _credentials_not_persisted(source)
        jobs = _jobs(source)
        # Detect ambiguity before a missing expected name can mask it.
        for name in jobs:
            if name in seen:
                raise ValueError("AMBIGUOUS_CROSS_WORKFLOW_CHECK: " + name)
            seen.add(name)
        if expected not in jobs:
            raise ValueError("REQUIRED_JOB_ID_MISSING: " + expected)
        _non_skippable_required_job(source, expected)
    return seen


class RequiredCIIdentities(unittest.TestCase):
    @staticmethod
    def actual():
        return {path: (ROOT / path).read_text(encoding="utf-8")
                for path in EXPECTED}

    def test_actual_required_contexts_unique_and_unfiltered(self):
        jobs = validate(self.actual())
        self.assertIn("security-regression", jobs)
        self.assertIn("failover-regression", jobs)
        self.assertIn("stress", jobs)

    def test_checkout_credentials_not_persisted_in_all_required_workflows(self):
        for path, source in self.actual().items():
            with self.subTest(workflow=path):
                self.assertTrue(_credentials_not_persisted(source))

    def test_reject_checkout_without_explicit_persistence_false(self):
        original = self.actual()[CORE]
        for unsafe in ("persist-credentials: true",
                       "persist-credentials: 'false'",
                       "persist-credentials: FALSE",
                       "credential-persistence: false"):
            with self.subTest(unsafe=unsafe):
                damaged = original.replace("persist-credentials: false",
                                           unsafe)
                with self.assertRaisesRegex(
                        ValueError, "PERSISTED_CHECKOUT_CREDENTIALS"):
                    _credentials_not_persisted(damaged)

    def test_checkout_false_in_later_step_does_not_count(self):
        original = self.actual()[FAILOVER]
        missing = original.replace(
            "        with:\n          persist-credentials: false\n", "", 1)
        # False inside setup-python belongs to a different step.
        misleading = missing.replace(
            "        with:\n          python-version: '3.12'",
            "        with:\n          persist-credentials: false\n"
            "          python-version: '3.12'", 1)
        with self.assertRaisesRegex(
                ValueError, "PERSISTED_CHECKOUT_CREDENTIALS"):
            _credentials_not_persisted(misleading)

    def test_reject_duplicate_regression_context(self):
        originals = self.actual()
        damaged = dict(originals)
        damaged[FAILOVER] = damaged[FAILOVER].replace(
            "  failover-regression:", "  security-regression:", 1)
        with self.assertRaisesRegex(ValueError, "AMBIGUOUS_CROSS_WORKFLOW_CHECK"):
            validate(damaged)

    def test_reject_missing_mandatory_job(self):
        originals = self.actual()
        damaged = dict(originals)
        damaged[CORE] = damaged[CORE].replace(
            "  security-regression:", "  renamed-for-test-only:", 1)
        with self.assertRaisesRegex(ValueError, "REQUIRED_JOB_ID_MISSING"):
            validate(damaged)

    def test_reject_pull_request_path_filter(self):
        originals = self.actual()
        damaged = dict(originals)
        damaged[FAILOVER] = damaged[FAILOVER].replace(
            "  pull_request:\n", "  pull_request:\n    paths:\n      - 'ops/**'\n", 1)
        with self.assertRaisesRegex(ValueError, "PR_TRIGGER_FILTERED"):
            validate(damaged)

    def test_reject_missing_pr_trigger(self):
        originals = self.actual()
        damaged = dict(originals)
        damaged[CORE] = damaged[CORE].replace(
            "  pull_request:\n", "  never_trigger:\n", 1)
        with self.assertRaisesRegex(ValueError, "PR_TRIGGER_MISSING"):
            validate(damaged)

    def test_reject_conditional_or_ignored_required_job(self):
        originals = self.actual()
        for key in (CORE, FAILOVER):
            required = EXPECTED[key]
            for bypass in ("    if: false\n",
                           "    continue-on-error: true\n"):
                with self.subTest(workflow=key, bypass=bypass):
                    damaged = dict(originals)
                    damaged[key] = damaged[key].replace(
                        "  " + required + ":\n",
                        "  " + required + ":\n" + bypass, 1)
                    with self.assertRaisesRegex(
                            ValueError, "CONDITIONAL_OR_IGNORED_REQUIRED_CHECK"):
                        validate(damaged)

    def test_reject_test_step_continue_on_error(self):
        originals = self.actual()
        anchors = {
            CORE: "      - name: Run all zero-cost synthetic regression tests\n",
            FAILOVER: "      - name: Run complete ops regression suite including outage simulations\n",
        }
        for key, anchor in anchors.items():
            with self.subTest(workflow=key):
                damaged = dict(originals)
                damaged[key] = damaged[key].replace(
                    anchor, anchor + "        continue-on-error: true\n", 1)
                with self.assertRaisesRegex(
                        ValueError, "CONDITIONAL_OR_IGNORED_REQUIRED_CHECK"):
                    validate(damaged)

    def test_reject_additional_privileged_pr_event(self):
        originals = self.actual()
        for key in (CORE, FAILOVER):
            with self.subTest(workflow=key):
                damaged = dict(originals)
                damaged[key] = damaged[key].replace(
                    "on:\n", "on:\n  pull_request_target:\n", 1)
                with self.assertRaisesRegex(ValueError, "UNSAFE_WORKFLOW_EVENT"):
                    validate(damaged)

    def test_reject_write_or_broad_workflow_permissions(self):
        originals = self.actual()
        for key in (CORE, FAILOVER):
            for unsafe in ("permissions:\n  contents: write\n",
                           "permissions:\n  contents: read\n  actions: write\n",
                           "permissions: write-all\n",
                           "permissions:\n  contents: read\n  id-token: write\n"):
                with self.subTest(workflow=key, unsafe=unsafe):
                    damaged = dict(originals)
                    damaged[key] = damaged[key].replace(
                        "permissions:\n  contents: read\n", unsafe, 1)
                    with self.assertRaisesRegex(
                            ValueError, "UNSAFE_TOKEN_PERMISSIONS"):
                        validate(damaged)

    def test_reject_job_permission_escalation(self):
        originals = self.actual()
        for key in (CORE, FAILOVER):
            with self.subTest(workflow=key):
                damaged = dict(originals)
                required = EXPECTED[key]
                damaged[key] = damaged[key].replace(
                    "  " + required + ":\n",
                    "  " + required + ":\n    permissions:\n      contents: write\n",
                    1)
                with self.assertRaisesRegex(
                        ValueError, "UNSAFE_TOKEN_PERMISSIONS"):
                    validate(damaged)

    def test_reject_secret_and_github_token_reference(self):
        originals = self.actual()
        for key in (CORE, FAILOVER):
            for source_expr in ("$" + "{{ secrets.TEST_API_KEY }}",
                                "$" + "{{ github.token }}"):
                with self.subTest(workflow=key, token=source_expr):
                    damaged = dict(originals)
                    damaged[key] += "\n# source expression test\n"
                    damaged[key] += "env:\n  EXAMPLE_TOKEN: " + source_expr + "\n"
                    with self.assertRaisesRegex(
                            ValueError, "UNSAFE_TOKEN_REFERENCE"):
                        validate(damaged)

    def test_reject_mutable_action_tag(self):
        originals = self.actual()
        for key in (CORE, FAILOVER):
            with self.subTest(workflow=key):
                damaged = dict(originals)
                damaged[key] = damaged[key].replace(
                    "uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
                    "uses: actions/checkout@v4", 1)
                with self.assertRaisesRegex(ValueError, "MUTABLE_ACTION_REFERENCE"):
                    validate(damaged)

    def test_reject_mutable_named_setup_action(self):
        originals = self.actual()
        for key in (CORE, FAILOVER):
            with self.subTest(workflow=key):
                damaged = dict(originals)
                damaged[key] = damaged[key].replace(
                    "uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065",
                    "uses: actions/setup-python@v5", 1)
                with self.assertRaisesRegex(ValueError, "MUTABLE_ACTION_REFERENCE"):
                    validate(damaged)

    def test_reject_missing_workflow(self):
        data = self.actual()
        del data[FAILOVER]
        with self.assertRaisesRegex(ValueError, "REQUIRED_WORKFLOW_MISSING"):
            validate(data)

    def test_reject_empty_job_block(self):
        with self.assertRaisesRegex(ValueError, "NO_WORKFLOW_JOBS"):
            _jobs("on:\n  pull_request:\n")


if __name__ == "__main__":
    unittest.main()
