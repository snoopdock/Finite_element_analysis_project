#!/usr/bin/env python3
"""Conservative bridge from the legacy knowledge base to the concept graph."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from core.knowledge_graph import ensure_graph_state if False else normalize_concept, normalize_proposition, new_graph_id
