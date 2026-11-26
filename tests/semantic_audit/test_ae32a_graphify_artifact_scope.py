from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from audit_engine.semantic_audit.ae32a.audit import audit_repository


class GraphifyArtifactScopeTests(unittest.TestCase):
    def test_graphify_outputs_are_excluded_from_source_evidence_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "src").mkdir()
            (root / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
            graphify = root / "branch-graphify-results" / "latest" / "main"
            graphify.mkdir(parents=True)
            (graphify / "graph.json").write_text('{"nodes": [], "edges": []}\n', encoding="utf-8")
            (graphify / "GRAPH_REPORT.md").write_text("# Graphify report\n", encoding="utf-8")
            (graphify / "graph.html").write_text("<html></html>\n", encoding="utf-8")
            ordinary = root / "reports"
            ordinary.mkdir()
            (ordinary / "graph.json").write_text('{"audit_input": true}\n', encoding="utf-8")

            report = audit_repository(root)
            paths = {row["path"]: row for row in report["source_manifest"]}

            self.assertEqual(report["audit"]["status"], "complete")
            self.assertIn("src/app.py", paths)
            self.assertIn("reports/graph.json", paths)
            self.assertEqual(paths["reports/graph.json"]["status"], "included")
            self.assertFalse(any(path.startswith("branch-graphify-results/") for path in paths))
            self.assertEqual(
                report["audit"]["scope_policy"]["excluded_generated_artifact_prefixes"],
                ["branch-graphify-results/"],
            )
            self.assertEqual(report["scope_issues"], [])

    def test_graphify_exclusion_is_directory_scoped_not_filename_scoped(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "branch-graphify-results" / "latest").mkdir(parents=True)
            (root / "branch-graphify-results" / "latest" / "graph.json").write_text("{}\n", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "graph.json").write_text('{"source": true}\n', encoding="utf-8")

            report = audit_repository(root)
            paths = {row["path"]: row for row in report["source_manifest"]}

            self.assertNotIn("branch-graphify-results/latest/graph.json", paths)
            self.assertEqual(paths["src/graph.json"]["status"], "included")


if __name__ == "__main__":
    unittest.main()
