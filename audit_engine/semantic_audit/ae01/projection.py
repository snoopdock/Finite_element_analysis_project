"""Reproducible bounded architecture evidence projection from the canonical graph."""
from __future__ import annotations
from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph


def project_imports(global_policy_graph: SemanticGraph, module_id: str) -> SemanticGraph:
    selected_edges = [edge for edge in global_policy_graph.edges
                      if edge.source_id == module_id and edge.relation_type == 'IMPORTS']
    nodes = {module_id} | {edge.target_id for edge in selected_edges}
    selected_nodes = [node for node in global_policy_graph.nodes if node.node_id in nodes]
    return SemanticGraph(nodes=selected_nodes, edges=selected_edges)
