# Milestone 06 Discovery Package v3

Run the dispatcher with:

pytest tests/test_milestone06_repository_interfaces.py -v -s

The -s flag is required so GitHub Actions logs show discovery output.

The output will provide:
- class names
- signatures
- annotations
- dataclass fields

This information is required before implementing the Document -> LaTeX IR adapter.
