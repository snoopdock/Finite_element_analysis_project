"""Condition-specific tool access policy for AE-32C matched experiments."""

# All five tools expose relationships projected from the repository SemanticGraph.
# The source-only control withholds this complete family; the treatment receives it.
GRAPH_DERIVED_TOOL_NAMES = frozenset({
    "graph_neighbors",
    "graph_path",
    "trace_execution_context",
    "find_related_tests",
    "find_workflow_context",
})
