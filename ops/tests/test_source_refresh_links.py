"""Exercise archive-to-site links and the actual workflow publication condition."""
import ast
import re
import unittest
from pathlib import Path


WORKFLOWS = Path(__file__).resolve().parents[2] / ".github/workflows"


def publish_allowed(workflow, context):
    """Evaluate the condition's boolean/comparison subset against event fixtures.

    Unsupported expressions fail the test instead of being assumed to allow or
    deny publication. No Python eval or external YAML dependency is needed.
    """
    job = workflow.split("  publish:", 1)[1]
    expression = re.search(r"^    if:\s*\$\{\{(.*?)\}\}\s*$", job, re.MULTILINE).group(1)
    expression = expression.replace("||", " or ").replace("&&", " and ").strip()

    def evaluate(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name) and node.id == "github":
            return context
        if isinstance(node, ast.Attribute):
            parent = evaluate(node.value)
            return parent.get(node.attr) if isinstance(parent, dict) else None
        if isinstance(node, ast.BoolOp):
            values = (bool(evaluate(item)) for item in node.values)
            if isinstance(node.op, ast.And):
                return all(values)
            if isinstance(node.op, ast.Or):
                return any(values)
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            left, right = evaluate(node.left), evaluate(node.comparators[0])
            if isinstance(node.ops[0], ast.Eq):
                return left == right
            if isinstance(node.ops[0], ast.NotEq):
                return left != right
        raise AssertionError("Unsupported workflow condition: " + ast.dump(node))

    return bool(evaluate(ast.parse(expression, mode="eval").body))


class SourceRefreshLinksTests(unittest.TestCase):
    def setUp(self):
        self.website = (WORKFLOWS / "football-king-iphone.yml").read_text(encoding="utf-8")

    def event(self, event_name="workflow_run", **run_fields):
        run = {
            "conclusion": "success",
            "head_branch": "main",
            "head_repository": {"full_name": "CHANCHUNWA1989/football-king-report"},
        }
        run.update(run_fields)
        return {
            "event_name": event_name,
            "repository": "CHANCHUNWA1989/football-king-report",
            "event": {"repository": {"default_branch": "main"}, "workflow_run": run},
        }

    def test_consumed_source_archives_trigger_website_refresh(self):
        website = self.website
        subscriptions = website.split("  workflow_run:", 1)[1].split("  push:", 1)[0]
        sources = {
            "football-king-bsd-free.yml": "sources/bsd_market_latest.json",
            "football-king-weather.yml": "sources/weather_latest.json",
            "football-king-wide-free.yml": "sources/wide_latest.json",
            "football-king-research-extensions.yml": "sources/research_extensions_latest.json",
            "football-king-japan-free-market.yml": "market/japan_free_status.json",
        }
        for filename, artifact in sources.items():
            with self.subTest(collector=filename):
                collector = (WORKFLOWS / filename).read_text(encoding="utf-8")
                name = re.search(r"^name:\s*(.+)$", collector, re.MULTILINE).group(1)
                self.assertIn(artifact, website, "Source must already be consumed by the website")
                self.assertIn(name, subscriptions, "Successful archive must trigger website refresh")

    def test_successful_main_repository_collector_is_allowed(self):
        self.assertTrue(publish_allowed(self.website, self.event()))

    def test_failed_or_incomplete_archive_does_not_publish(self):
        for conclusion in ("failure", "cancelled", "timed_out", "skipped", "action_required", None):
            with self.subTest(conclusion=conclusion):
                self.assertFalse(publish_allowed(self.website, self.event(conclusion=conclusion)))

    def test_other_branches_do_not_publish(self):
        for branch in ("research/source-update", "release", "", None):
            with self.subTest(branch=branch):
                self.assertFalse(publish_allowed(self.website, self.event(head_branch=branch)))

    def test_fork_or_missing_repository_does_not_publish(self):
        for repo in ({"full_name": "another-owner/football-king-report"}, {}, None):
            with self.subTest(repository=repo):
                self.assertFalse(publish_allowed(self.website, self.event(head_repository=repo)))

    def test_manual_push_and_scheduled_updates_still_work_without_run_payload(self):
        for event_name in ("workflow_dispatch", "push", "schedule"):
            with self.subTest(event_name=event_name):
                event = self.event(event_name)
                del event["event"]["workflow_run"]
                self.assertTrue(publish_allowed(self.website, event))

    def test_source_events_filter_main_and_checkout_trusted_default(self):
        subscription = self.website.split("  workflow_run:", 1)[1].split("  push:", 1)[0]
        self.assertRegex(subscription, r"(?m)^    branches: \[main\]$")
        self.assertIn("types: [completed]", subscription)
        checkout = self.website.split("- name: Checkout trusted program and safety modules", 1)[1]
        checkout = checkout.split("\n      - name:", 1)[0]
        self.assertNotIn("ref:", checkout, "Never checkout triggering collector's code")
        self.assertIn("persist-credentials: false", checkout)


if __name__ == "__main__":
    unittest.main()
