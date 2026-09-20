"""
L1-L23-L first contract test.

Boundary:

Document Model -> LaTeX IR -> Renderer

This test intentionally protects the boundary without
introducing new architecture.
"""

import copy

from processing.latex_renderer import render_body

try:
    from processing.latex_ir import build_document_model
except ImportError:
    build_document_model = None


def _create_document():
    assert build_document_model is not None, (
        "Update this import according to the repository's existing "
        "LaTeX IR construction API."
    )

    return build_document_model(
        {
            "title": "Contract Test",
            "objective": "Validate deterministic rendering of a semantic document boundary.",
            "metadata": {
                "source": "L1-L23-L",
            },
        },
        [
            {
                "title": "Boundary",
                "blocks": [
                    {
                        "type": "text",
                        "text": "A & B",
                    },
                    {
                        "type": "math",
                        "expression": r"x^2+y^2",
                    },
                ],
            }
        ],
        [],
    )


def test_document_to_renderer_is_deterministic():
    first = _create_document()
    second = _create_document()

    assert first == second

    assert render_body(first) == render_body(second)


def test_renderer_does_not_mutate_semantic_document():
    document = _create_document()

    before = copy.deepcopy(document)

    render_body(document)

    assert document == before
