#!/usr/bin/env python3
"""State management utilities."""

import pathlib

from utils.text import load_json, save_json


def initialize_state(paths, config):
    """Initialize pipeline state."""
    state = load_json(paths["state"], {
        "topic": config.get("topic", ""),
        "objective": config.get("objective", ""),
        "cycle": 0,
        "iteration": 0,
        "processed_sources": [],
        "processed_sources_extracted": [],
        "knowledge_base": {},
        "sections": [],
    })
    
    for k in ["processed_sources", "processed_sources_extracted"]:
        state.setdefault(k, [])
    state.setdefault("knowledge_base", {})
    state.setdefault("sections", [])
    
    return state


def save_state(paths, state):
    """Save pipeline state to disk."""
    save_json(paths["state"], state)
