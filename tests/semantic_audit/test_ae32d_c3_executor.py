"""Provider-free structural tests for the AE-45 retained-snapshot executor."""
import ast
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools.ae32d_c3_executor import (
    _build_investigator_limits,
    _compare_graph_snapshot,
    prepare_c3_execution,
)


SOURCE_SHA = "a" * 40
MANIFEST = "b" * 64
FINGERPRINT = "graph:" + "c" * 32


def snapshot():
    return {
        "source_revision": SOURCE_SHA,
        "source_manifest_sha256": MANIFEST,
        "graph_fingerprint": FINGERPRINT,
        "graph_projection_version": "ae32b/source-evidence-projection/v3",
        "evidence_index_status": "complete",
        "graph_backend": "networkx",
        "graph_node_count": 4,
        "graph_edge_count": 3,
        "backend_pipeline_wired": True,
    }


def contract(status="ready_for_c3_executor"):
    return {
        "status": status,
        "case_id": "AE32D-EXECUTOR-TEST",
        "source_commit_sha": SOURCE_SHA,
        "source_manifest_sha256": MANIFEST,
        "graph_fingerprint": FINGERPRINT,
        "provider_name": "cloudflare",
        "model_name": "@cf/qwen/qwen3.8-27b",
        "investigator_problem": "Inspect the pinned source.",
        "investigator_limits": {
            "max_rounds": 11,
            "max_tool_calls": 12,
            "max_tokens_per_call": 2048,
            "finalization_max_tokens_per_call": 6144,
            "max_total_tokens": 30720,
            "max_elapsed_seconds": 900,
            "max_cost_usd": 0.50,
            "temperature": 0.0,
        },
        "investigation_requirements": {
            "required_source_paths": ["loader.py"],
            "required_graph_target": "loader.py",
            "required_graph_relation_types": ["CALLS", "DEFINES"],
            "required_graph_direction": "both",
            "require_graph_interaction": True,
            "require_complete_investigation_context": True,
            "prefetch_required_graph_query": True,
            "required_context_target": "loader.py",
            "required_context_paths": ["context.md"],
            "prefetch_required_context_trace": True,
        },
    }


def inputs():
    graph = snapshot()
    return (
        {"source": {"source_commit_sha": SOURCE_SHA, "fixture_path": "fixtures/case"}},
        {
            "source_commit_sha": SOURCE_SHA,
            "baseline_report": {"source_manifest_digest": MANIFEST},
            "graph_snapshot": graph,
        },
        {"request": {"investigator_problem": "Inspect the pinned source."}},
        {
            "status": "verified",
            "expected_graph_snapshot": dict(graph),
            "observed_graph_snapshot": dict(graph),
        },
        {"approved": True},
    )


class FakeEvidenceTools:
    def __init__(self, *_args, **_kwargs):
        self.file_hashes = {"loader.py": "d" * 64, "context.md": "e" * 64}
        self.manifest_sha256 = MANIFEST
        self.graph_fingerprint = FINGERPRINT
        self.closed = False
        self.report = {}

    def invoke(self, name, arguments):
        assert name == "repository_summary"
        assert arguments == {}
        graph = snapshot()
        return {
            "status": "ok",
            "provenance": {
                "source_revision": SOURCE_SHA,
                "source_manifest_sha256": MANIFEST,
                "graph_fingerprint": FINGERPRINT,
                "graph_projection_version": graph["graph_projection_version"],
            },
            "result": {
                "evidence_index_status": "complete",
                "graph_node_count": 4,
                "graph_edge_count": 3,
                "graph_runtime": {
                    "active_computation_backend": "networkx",
                    "backend_pipeline_wired_into_ae32b_query_path": True,
                },
            },
        }

    def close(self):
        self.closed = True


class C3ExecutorTests(unittest.TestCase):
    def test_limit_mapping_preserves_authorized_values_and_explicit_fixed_bounds(self):
        limits = _build_investigator_limits(contract()["investigator_limits"])
        self.assertEqual(limits.max_rounds, 11)
        self.assertEqual(limits.max_tool_calls, 12)
        self.assertEqual(limits.max_tokens_per_call, 2048)
        self.assertEqual(limits.finalization_max_tokens_per_call, 6144)
        self.assertEqual(limits.max_total_tokens, 30720)
        self.assertEqual(limits.max_elapsed_seconds, 900)
        self.assertEqual(limits.max_cost_usd, 0.50)
        self.assertEqual(limits.temperature, 0.0)
        self.assertEqual(limits.max_snapshot_files, 100)
        self.assertEqual(limits.max_snapshot_bytes, 2_000_000)

    def test_limit_mapping_rejects_missing_or_extra_contract_fields(self):
        values = contract()["investigator_limits"]
        with self.assertRaisesRegex(ValueError, "limit_fields_mismatch"):
            _build_investigator_limits({**values, "max_total_tokens": 180_000})
        with self.assertRaisesRegex(ValueError, "limit_fields_mismatch"):
            _build_investigator_limits({key: value for key, value in values.items() if key != "max_cost_usd"})

    def test_snapshot_comparison_checks_every_b_and_c2_field(self):
        observed = snapshot()
        expected = snapshot()
        for key in observed:
            changed = dict(observed)
            changed[key] = "tampered"
            with self.subTest(field=key):
                with self.assertRaises(ValueError):
                    _compare_graph_snapshot(changed, expected)

    def test_unconfirmed_contract_blocks_before_graph_construction(self):
        task, b_report, package, c2, authorization = inputs()
        with patch("tools.ae32d_c3_executor.build_c3_execution_contract",
                   return_value=contract("ready_for_manual_confirmation")), \
             patch("tools.ae32d_c3_executor.RepositoryEvidenceTools") as tools_factory, \
             patch("tools.ae32d_c3_executor._scope_snapshot") as scope:
            with self.assertRaisesRegex(ValueError, "contract_not_authorized"):
                prepare_c3_execution(
                    task, b_report, package, c2, authorization, tempfile.gettempdir(),
                    manual_dispatch_confirmed=False,
                )
        tools_factory.assert_not_called()
        scope.assert_not_called()

    def test_checkout_mismatch_blocks_before_graph_construction(self):
        task, b_report, package, c2, authorization = inputs()
        with tempfile.TemporaryDirectory() as root, \
             patch("tools.ae32d_c3_executor.build_c3_execution_contract", return_value=contract()), \
             patch("tools.ae32d_c3_executor._git_head", return_value="f" * 40), \
             patch("tools.ae32d_c3_executor.RepositoryEvidenceTools") as tools_factory:
            with self.assertRaisesRegex(ValueError, "checkout_revision_mismatch"):
                prepare_c3_execution(
                    task, b_report, package, c2, authorization, root,
                    manual_dispatch_confirmed=True,
                )
        tools_factory.assert_not_called()

    def test_retained_snapshot_session_builds_investigator_without_creating_provider(self):
        task, b_report, package, c2, authorization = inputs()
        fake_tools = FakeEvidenceTools()
        cost_module = SimpleNamespace(
            build_live_cost_estimator=lambda provider, model: (
                lambda _p, _m, _chars, _tokens: 0.001
            )
        )
        with tempfile.TemporaryDirectory() as root, \
             patch("tools.ae32d_c3_executor.build_c3_execution_contract", return_value=contract()), \
             patch("tools.ae32d_c3_executor._git_head", return_value=SOURCE_SHA), \
             patch("tools.ae32d_c3_executor._scope_snapshot",
                   return_value={"digest": MANIFEST, "issues": []}), \
             patch("tools.ae32d_c3_executor.RepositoryEvidenceTools", return_value=fake_tools), \
             patch("tools.ae32d_c3_executor._runner_revision", return_value="f" * 40), \
             patch.dict(sys.modules, {
                 "audit_engine.semantic_audit.ae32c.live_evaluation": cost_module
             }), \
             patch("tools.ae32d_c3_executor.RepositoryInvestigator") as investigator_factory:
            session = prepare_c3_execution(
                task, b_report, package, c2, authorization, root,
                manual_dispatch_confirmed=True,
            )
            self.assertIs(session.evidence_tools, fake_tools)
            self.assertEqual(session.evidence_tools.graph_fingerprint, FINGERPRINT)
            self.assertEqual(session.limits.max_total_tokens, 30_720)
            self.assertEqual(session.contract["investigator_problem"], "Inspect the pinned source.")
            self.assertFalse(fake_tools.closed)

            provider = object()
            investigator_factory.return_value = Mock()
            session.build_investigator(provider)
            kwargs = investigator_factory.call_args.kwargs
            self.assertIs(kwargs["provider"], provider)
            self.assertIs(kwargs["evidence_tools"], fake_tools)
            self.assertEqual(kwargs["source_revision"], SOURCE_SHA)
            self.assertEqual(kwargs["required_source_paths"], ("loader.py",))
            self.assertEqual(kwargs["required_context_paths"], ("context.md",))
            self.assertEqual(kwargs["limits"].max_total_tokens, 30_720)
            self.assertEqual(kwargs["cost_estimator"]("cloudflare", "@cf/qwen/qwen3.8-27b", 1, 1), 0.001)
            session.close()
            self.assertTrue(fake_tools.closed)
            with self.assertRaisesRegex(RuntimeError, "session_closed"):
                session.build_investigator(provider)
            session.close()

    def test_scope_mismatch_closes_graph_and_fails_closed(self):
        task, b_report, package, c2, authorization = inputs()
        fake_tools = FakeEvidenceTools()
        cost_module = SimpleNamespace(
            build_live_cost_estimator=lambda *_args: (lambda *_values: 0.001)
        )
        with tempfile.TemporaryDirectory() as root, \
             patch("tools.ae32d_c3_executor.build_c3_execution_contract", return_value=contract()), \
             patch("tools.ae32d_c3_executor._git_head", return_value=SOURCE_SHA), \
             patch("tools.ae32d_c3_executor._scope_snapshot",
                   return_value={"digest": "0" * 64, "issues": []}), \
             patch("tools.ae32d_c3_executor.RepositoryEvidenceTools", return_value=fake_tools), \
             patch.dict(sys.modules, {
                 "audit_engine.semantic_audit.ae32c.live_evaluation": cost_module
             }):
            with self.assertRaisesRegex(ValueError, "declared_scope_manifest_mismatch"):
                prepare_c3_execution(
                    task, b_report, package, c2, authorization, root,
                    manual_dispatch_confirmed=True,
                )
        self.assertTrue(fake_tools.closed)

    def test_module_has_no_eager_provider_factory_or_credential_import(self):
        source = Path(__file__).parents[2] / "tools" / "ae32d_c3_executor.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        self.assertFalse(any(name == "providers" or name.startswith("providers.") for name in imported))
        self.assertFalse(any("credential" in name.casefold() for name in imported))


if __name__ == "__main__":
    unittest.main()
