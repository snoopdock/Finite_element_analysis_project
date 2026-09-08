"""
Semantic graph construction and serialization package.

Responsibilities:

- Convert audit observations into semantic graphs.
- Persist semantic graph representations.

Future extensions:

- NetworkX backend
- RDF export
- OWL ontology mapping
- graph reasoning
"""

from .builder import (
    SemanticGraphBuilder
)

from .serializer import (
    serialize_graph
)


__all__ = [

    "SemanticGraphBuilder",

    "serialize_graph"

]
