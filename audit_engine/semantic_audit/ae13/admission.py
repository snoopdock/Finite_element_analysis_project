"""Complete admission validation for the existing mutable SemanticGraph.

Does not change the canonical graph model or claim that a structurally valid
semantic graph has accurate Python semantics.
"""
from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.graph.analysis.identity import graph_fingerprint
from .identity import canonical


def validate_graph(graph: SemanticGraph) -> dict:
    if not isinstance(graph, SemanticGraph):
        raise ValueError('Not a canonical SemanticGraph')
    ids = set()
    for node in graph.nodes:
        if not isinstance(node.node_id, str) or not node.node_id.strip() or node.node_id in ids:
            raise ValueError('Empty or duplicate graph node')
        if not isinstance(node.entity_type, str) or not node.entity_type.strip():
            raise ValueError('Empty graph node type')
        canonical(node.attributes)
        canonical(node.metadata)
        ids.add(node.node_id)
    seen_occurrences = set()
    for edge in graph.edges:
        if not isinstance(edge.source_id,str) or not isinstance(edge.target_id,str) or edge.source_id not in ids or edge.target_id not in ids:
            raise ValueError('Dangling graph edge')
        if not isinstance(edge.relation_type,str) or not edge.relation_type.strip():
            raise ValueError('Empty graph relation')
        canonical(edge.attributes)
        canonical(edge.metadata)
        occurrence = edge.metadata.get('ae13_occurrence_id')
        if occurrence is not None:
            if not isinstance(occurrence,str) or not occurrence or occurrence in seen_occurrences:
                raise ValueError('Duplicate/invalid edge occurrence identifier')
            seen_occurrences.add(occurrence)
    return {'graph_fingerprint':graph_fingerprint(graph),'nodes':len(ids),'edges':len(graph.edges),
            'edge_occurrences':len(seen_occurrences)}
