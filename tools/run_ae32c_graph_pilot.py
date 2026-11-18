#!/usr/bin/env python3
"""Run the matched AE-32C graph-enabled/graph-disabled repository pilot."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit_engine.semantic_audit.ae32c.graph_pilot import main


if __name__ == "__main__":
    raise SystemExit(main())
