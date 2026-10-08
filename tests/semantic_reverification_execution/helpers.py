from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.evolution import IncrementalReverificationService, SemanticGraphEvolutionService


def make_graph(*, target_lifecycle="experimental", add_extra=False, remove_edge=False, edge_source="code:1"):
    graph = SemanticGraph()
    graph.add_node(SemanticNode("prod", "Module", attributes={"lifecycle": "production"}))
    graph.add_node(SemanticNode("exp", "Module", attributes={"lifecycle": target_lifecycle}))
    graph.add_node(SemanticNode("other", "Module", attributes={"lifecycle": "stable"}))
    if not remove_edge:
        graph.add_edge(SemanticEdge("prod", "exp", "DEPENDS_ON", metadata={"source_id": edge_source}))
    if add_extra:
        graph.add_edge(SemanticEdge("prod", "other", "DEPENDS_ON", metadata={"source_id": "code:2"}))
    return graph


def build_transition(before_graph, after_graph, semantic_context, artifacts):
    evolution = SemanticGraphEvolutionService().compare(
        before_graph=before_graph,
        after_graph=after_graph,
        before_context=semantic_context,
        artifacts=artifacts,
    )
    assessment = IncrementalReverificationService().assess(
        evolution=evolution,
        artifacts=artifacts,
    )
    return evolution, assessment
