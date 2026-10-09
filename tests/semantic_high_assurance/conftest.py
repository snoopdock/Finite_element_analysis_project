from __future__ import annotations

import hashlib

import pytest

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.analysis import SemanticContext
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.verification import VerificationObligation


@pytest.fixture
def semantic_graph():
    graph = SemanticGraph()
    graph.add_node(SemanticNode("module-a", "Module"))
    graph.add_node(SemanticNode("module-b", "Module"))
    graph.add_edge(SemanticEdge("module-a", "module-b", "DEPENDS_ON", metadata={"source_id": "code:a"}))
    return graph


@pytest.fixture
def analysis_result(semantic_graph):
    context = SemanticContext(relationship_vocabulary_version="repo-relations/v1")
    return SemanticGraphAnalysisService(semantic_graph, semantic_context=context).analyze(
        GraphQuery("g340-analysis", QueryType.DEPENDENCY, ["module-a"], {"max_depth": 1})
    )


def static_import_obligation(analysis_result, source_text: str, forbidden=None):
    return VerificationObligation.from_analysis_result(
        analysis_result,
        obligation_type="python_static_import_constraint",
        requested_verifier_ids=("python-static-import",),
        parameters={
            "source_text": source_text,
            "forbidden_modules": list(forbidden or ["networkx"]),
            "timeout_ms": 1000,
        },
    )


def digest_obligation(analysis_result, content: str, expected: str | None = None):
    expected = expected or hashlib.sha256(content.encode("utf-8")).hexdigest()
    return VerificationObligation.from_analysis_result(
        analysis_result,
        obligation_type="artifact_digest_match",
        requested_verifier_ids=("artifact-digest-integrity",),
        parameters={
            "content": content,
            "expected_sha256": expected,
            "timeout_ms": 1000,
        },
    )
