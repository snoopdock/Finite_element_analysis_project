"""
Milestone 06 - Repository Interface Discovery

No production code changes are made by this package.
This discovers the real repository interfaces before adapter implementation.
"""

import inspect


def test_document_model_interface_discovery():
    import core.document_model as document_model
    print("\n=== core.document_model ===")
    for name, obj in inspect.getmembers(document_model, inspect.isclass):
        print(name, inspect.signature(obj))
    assert hasattr(document_model, "__file__")


def test_latex_ir_interface_discovery():
    import processing.latex_ir as latex_ir
    print("\n=== processing.latex_ir ===")
    for name, obj in inspect.getmembers(latex_ir, inspect.isclass):
        print(name, inspect.signature(obj))
    assert hasattr(latex_ir, "__file__")


def test_pipeline_interface_discovery():
    import core.pipeline as pipeline
    print("\n=== core.pipeline ===")
    for name, obj in inspect.getmembers(pipeline, inspect.isfunction):
        print(name, inspect.signature(obj))
    assert hasattr(pipeline, "__file__")
