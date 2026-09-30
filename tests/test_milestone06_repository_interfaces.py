"""
Milestone 06 - Repository Interface Discovery v3

Extract repository interfaces needed for the semantic rendering adapter.
Run with pytest -s to show output.
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

    annotations = getattr(obj, "__annotations__", {})
    if annotations:
        print("ANNOTATIONS:")
        for key, value in annotations.items():
            print(f"  {key}: {value}")

    fields = getattr(obj, "__dataclass_fields__", {})
    if fields:
        print("DATACLASS FIELDS:")
        for key, field in fields.items():
            print(f"  {key}: {field.type}")


def discover_module(module, title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)

    for name, obj in inspect.getmembers(module, inspect.isclass):
        describe_class(name, obj)


def test_document_model_interface_discovery():
    import core.document_model as document_model
    discover_module(document_model, "core.document_model")
    assert hasattr(document_model, "__file__")


def test_latex_ir_interface_discovery():
    import processing.latex_ir as latex_ir
    discover_module(latex_ir, "processing.latex_ir")
    assert hasattr(latex_ir, "__file__")


def test_pipeline_interface_discovery():
    import core.pipeline as pipeline

    print("\n" + "=" * 60)
    print("core.pipeline FUNCTIONS")
    print("=" * 60)

    for name, obj in inspect.getmembers(pipeline, inspect.isfunction):
        try:
            print(f"{name}{inspect.signature(obj)}")
        except (TypeError, ValueError):
            print(name)

    assert hasattr(pipeline, "__file__")
