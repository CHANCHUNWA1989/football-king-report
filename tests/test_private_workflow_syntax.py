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
    def test_all_inline_python_compiles(self):
        programs = snippets()
        self.assertGreaterEqual(len(programs), 2)
        for i, program in enumerate(programs):
            with self.subTest(index=i):
                compile(program, str(WORKFLOW) + ":" + str(i), "exec")

if __name__ == "__main__":
    unittest.main()
