from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "tools" / "branch-graphify" / "run_analysis.py"
SPEC = importlib.util.spec_from_file_location("branch_graphify_run_analysis", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class BranchGraphifyTests(unittest.TestCase):
    def test_safe_name_is_stable_for_branch_slashes(self):
        self.assertEqual(MODULE.safe_name("stage1/section-uuids"), "stage1-section-uuids")

    def test_graph_collections_accepts_graphify_nodes_and_links(self):
        nodes, edges = MODULE.graph_collections({
            "graph": {"nodes": [{"id": "a"}], "links": [{"source": "a", "target": "b"}]}
        })
        self.assertEqual(nodes, [{"id": "a"}])
        self.assertEqual(edges, [{"source": "a", "target": "b"}])

    def test_graph_collections_rejects_malformed_collections(self):
        with self.assertRaises(ValueError):
            MODULE.graph_collections({"nodes": {}, "edges": []})

    def test_report_and_metadata_are_bound_to_one_branch_commit(self):
        metadata = {
            "branch": "stage1/section-uuids",
            "source_commit": "a" * 40,
            "graphify_version": "0.9.112",
            "generated_at_utc": "2026-11-26T00:00:00+00:00",
            "node_count": 12,
            "edge_count": 9,
            "graph_json_sha256": "b" * 64,
            "artifacts": {"html": "graph.html"},
            "interpretation_boundary": "Structural extraction only.",
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            MODULE.render_report(output, metadata)
            saved = json.loads((output / "run-metadata.json").read_text(encoding="utf-8"))
            report = (output / "analysis-report.md").read_text(encoding="utf-8")
            self.assertEqual(saved["branch"], "stage1/section-uuids")
            self.assertEqual(saved["source_commit"], "a" * 40)
            self.assertIn("does not compare branches", report)
            self.assertIn("does not establish runtime behavior", report)

    def test_script_exposes_single_branch_not_comparison_arguments(self):
        import inspect
        source = inspect.getsource(MODULE.main)
        self.assertIn('"--branch"', source)
        self.assertNotIn('"--compare"', source)
        self.assertNotIn('"--base"', source)


if __name__ == "__main__":
    unittest.main()
