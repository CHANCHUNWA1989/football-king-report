"""End-to-end research artifact job tests, with no live provider dependency."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ops.research_artifact_job import main

class ResearchArtifactJobTests(unittest.TestCase):
    def test_artifacts_are_hold_only(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            source=root/"export.json"
            source.write_text(json.dumps({"source":"offline-fixture-export","fixtures":[]}),encoding="utf-8")
            target=root/"artifacts"
            with patch("sys.argv",["research_artifact_job","--input",str(source),"--outdir",str(target)]):
                main()
            metadata=json.loads((target/"metadata.json").read_text(encoding="utf-8"))
            report=json.loads((target/"report.json").read_text(encoding="utf-8"))
            markdown=(target/"report.md").read_text(encoding="utf-8")
            self.assertEqual(metadata["production_recommendations"],"HOLD")
            self.assertFalse(metadata["positive_ev_verified"])
            self.assertFalse(metadata["source_independently_verified"])
            self.assertEqual(report["sample_count"],0)
            self.assertIn("HOLD",markdown)

    def test_invalid_source_does_not_create_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            source=root/"export.json"
            source.write_text('{"source":"","fixtures":[]}',encoding="utf-8")
            target=root/"artifacts"
            with patch("sys.argv",["research_artifact_job","--input",str(source),"--outdir",str(target)]):
                with self.assertRaises(ValueError):
                    main()
            self.assertFalse((target/"metadata.json").exists())

if __name__=="__main__":
    unittest.main()
