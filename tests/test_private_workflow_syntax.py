"""Compile inline Python in the actual live workflow before any billable API call."""
import unittest
from pathlib import Path
from textwrap import dedent

WORKFLOW = Path(".github/workflows/private-all-market-research.yml")

def snippets():
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    inside, script = False, []
    found = []
    for line in lines:
        if not inside and "python - <<'PY'" in line:
            inside = True
            script = []
        elif inside and line.strip() == "PY":
            found.append(dedent("\n".join(script) + "\n"))
            inside = False
        elif inside:
            script.append(line)
    if inside:
        raise ValueError("UNCLOSED_INLINE_PYTHON")
    return found

class TestLiveWorkflowSyntax(unittest.TestCase):
    def test_phone_refresh_requires_successful_private_collection(self):
        text = Path(".github/workflows/football-king-iphone.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_run:", text)
        self.assertIn("Football King private all-market research", text)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", text)
        self.assertIn("market/private_summary_latest.json", text)
        self.assertIn("ops.public_readiness_site", text)

    def test_all_inline_python_compiles(self):
        programs = snippets()
        self.assertGreaterEqual(len(programs), 2)
        for i, program in enumerate(programs):
            with self.subTest(index=i):
                compile(program, str(WORKFLOW) + ":" + str(i), "exec")

if __name__ == "__main__":
    unittest.main()
