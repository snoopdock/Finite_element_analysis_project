#!/usr/bin/env python3
"""Runtime audit for Stage 1 section identity and structural lineage."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.section_identity import ensure_section_id, normalize_sections


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        first = {"title": "Parent section", "content": "text"}
        original_id = ensure_section_id(first)
        same_id = ensure_section_id(first)
        _assert(same_id == original_id, "Existing section ID was not preserved.")

        children = normalize_sections([
            {
                "title": "Child A",
                "content": "a",
                "parent_section_ids": [original_id],
            },
            {
                "title": "Child B",
                "content": "b",
                "parent_section_ids": [original_id],
            },
        ])
        _assert(all(section.get("section_id") for section in children), "A child is missing section_id.")
        _assert(len({section["section_id"] for section in children}) == 2, "Sibling sections share an ID.")
        _assert(all(original_id in section.get("parent_section_ids", []) for section in children), "Split lineage was not retained.")

        merged = normalize_sections([{
            "title": "Merged section",
            "content": "merged",
            "parent_section_ids": [children[0]["section_id"], children[1]["section_id"]],
        }])
        merged_id = merged[0]["section_id"]
        _assert(merged_id not in {children[0]["section_id"], children[1]["section_id"]}, "Merge reused a parent ID.")
        _assert(set(merged[0]["parent_section_ids"]) == {children[0]["section_id"], children[1]["section_id"]}, "Merge lineage was not retained.")

        print("Stage 1 section identity runtime audit")
        print("=======================================")
        print(f"parent section: {original_id}")
        print(f"child sections: {len(children)}")
        print(f"merged section: {merged_id}")
        print("PASS: stable IDs and split/merge lineage checks passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 1 SECTION AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
