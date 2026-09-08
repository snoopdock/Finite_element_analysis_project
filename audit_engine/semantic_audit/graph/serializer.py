import json
from pathlib import Path

from ..core.semantic_graph import (
    SemanticGraph
)



def serialize_graph(
    graph: SemanticGraph,
    output_path: str = "semantic_graph.json"
) -> None:
    """
    Serialize SemanticGraph into JSON.

    The output format is designed to be:

    - human readable
    - machine processable
    - RDF compatible
    - future OWL mapping compatible
    """


    data = graph.to_dict()


    Path(
        output_path
    ).write_text(

        json.dumps(
            data,
            indent=2
        ),

        encoding="utf-8"

    )
