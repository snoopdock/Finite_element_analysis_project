"""
Milestone 06 - Document model to LaTeX IR projection tests.

These tests validate the first semantic boundary.
"""

from processing.document_model_to_latex_ir import (
    DocumentModelToLatexIR,
)


class FakeText:
    def __init__(self, text):
        self.text = text


class FakeSection:
    def __init__(self, title, children):
        self.title = title
        self.children = children


class FakeDocument:
    def __init__(self):
        self.metadata = {
            "topic": "test",
            "objective": "projection"
        }
        self.children = [
            FakeSection(
                "Introduction",
                [
                    FakeText("hello")
                ]
            )
        ]


def test_document_projects_to_latex_ir():

    document = FakeDocument()

    result = DocumentModelToLatexIR().project(document)

    assert result.topic == "test"
    assert len(result.sections) == 1
    assert result.sections[0].title == "Introduction"
    assert len(result.sections[0].blocks) == 1
    assert result.sections[0].blocks[0].text == "hello"
