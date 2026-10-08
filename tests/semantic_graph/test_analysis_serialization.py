import json

from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.analysis import AnalysisArtifactSerializer
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType


def test_analysis_artifact_is_json_serializable(software_graph):
    result = SemanticGraphAnalysisService(software_graph).analyze(
        GraphQuery("q", QueryType.DEPENDENCY, ["app.py"])
    )
    payload = AnalysisArtifactSerializer.bundle_to_dict([result])
    encoded = json.dumps(payload, sort_keys=True)
    assert "semantic_graph_analysis/v1" in encoded
    assert '"verification_status": "observed"' in encoded


def test_analysis_artifact_writer(tmp_path, software_graph):
    result = SemanticGraphAnalysisService(software_graph).analyze(
        GraphQuery("q", QueryType.DEPENDENCY, ["app.py"])
    )
    path = AnalysisArtifactSerializer.write_bundle(
        [result],
        tmp_path / "analysis.json",
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["result_count"] == 1
    assert payload["results"][0]["analysis_id"] == result.analysis_id
