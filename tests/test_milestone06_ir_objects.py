"""
Milestone 06 - LaTeX IR Object Discovery

Purpose:
Verify which semantic rendering objects already exist in processing.latex_ir
before extending the projection adapter.

No production code changes.
"""

import inspect


TARGET_OBJECTS = [
    "CitationBlock",
    "MathBlock",
    "CrossReferenceBlock",
    "DocumentBlock",
    "TextBlock",
    "SectionModel",
    "DocumentModel",
]


def test_latex_ir_semantic_objects_discovery():
    import processing.latex_ir as latex_ir

    print("\n========== processing.latex_ir target objects ==========")

    for name in TARGET_OBJECTS:
        obj = getattr(latex_ir, name, None)

        if obj is None:
            print(f"\n{name}: NOT FOUND")
            continue

        print(f"\n{name}: FOUND")
        print(f"MODULE: {obj.__module__}")

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

    assert hasattr(latex_ir, "__file__")
