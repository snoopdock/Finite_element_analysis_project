"""
Milestone 06 - Repository Interface Discovery v2

Purpose:
Discover repository interfaces before implementing the semantic rendering adapter.

This version avoids failing on classes where inspect.signature()
is unavailable (for example some exception subclasses).
"""

import inspect


def describe_class(name, obj):
    print(f"\nCLASS: {name}")
    print(f"MODULE: {obj.__module__}")
    print(f"BASES: {obj.__bases__}")

    try:
        print(f"SIGNATURE: {inspect.signature(obj)}")
    except (TypeError, ValueError):
        print("SIGNATURE: unavailable")

    annotations = getattr(obj, "__annotations__", None)
    if annotations:
        print(f"ANNOTATIONS: {annotations}")

    fields = getattr(obj, "__dataclass_fields__", None)
    if fields:
        print(f"DATACLASS FIELDS: {list(fields.keys())}")


def discover_module(module, title):
    print(f"\n========== {title} ==========")

    for name, obj in inspect.getmembers(module, inspect.isclass):
        describe_class(name, obj)


def test_document_model_interface_discovery():
    import core.document_model as document_model

    discover_module(
        document_model,
        "core.document_model"
    )

    assert hasattr(document_model, "__file__")


def test_latex_ir_interface_discovery():
    import processing.latex_ir as latex_ir

    discover_module(
        latex_ir,
        "processing.latex_ir"
    )

    assert hasattr(latex_ir, "__file__")


def test_pipeline_interface_discovery():
    import core.pipeline as pipeline

    print("\n========== core.pipeline FUNCTIONS ==========")

    for name, obj in inspect.getmembers(
        pipeline,
        inspect.isfunction
    ):
        print(f"\nFUNCTION: {name}")
        print(inspect.signature(obj))

    assert hasattr(pipeline, "__file__")
