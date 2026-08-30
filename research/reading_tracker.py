#!/usr/bin/env python3
"""
Reading Tracker - Records how much of each article has been read,
which sections were used, and what knowledge was extracted from each.
"""

import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional


TRACKER_FILE = Path("state/reading_state.json")


def load_reading_state() -> Dict:
    """Load the reading state from disk."""
    if TRACKER_FILE.exists():
        try:
            with open(TRACKER_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_reading_state(state: Dict):
    """Save the reading state to disk."""
    TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def mark_section_read(
    article_id: str,
    section_type: str,
    char_start: int,
    extracted_items: Dict[str, int],
    reading_state: Dict
) -> Dict:
    """
    Record that a section of an article has been read.
    
    Args:
        article_id: Unique identifier for the article
        section_type: Type of section (methodology, results, etc.)
        char_start: Starting character position of the section
        extracted_items: Dict of what was extracted, e.g. {"concepts": 3, "equations": 2, "rules": 1}
        reading_state: The current reading state dict
        
    Returns:
        Updated reading state
    """
    if article_id not in reading_state:
        reading_state[article_id] = {
            "first_read_at": datetime.now(timezone.utc).isoformat(),
            "read_sections": [],
            "section_details": [],
            "total_extractions": {
                "concepts": 0,
                "equations": 0,
                "procedures": 0,
                "rules": 0,
            }
        }
    
    article = reading_state[article_id]
    section_key = f"{section_type}_{char_start}"
    
    if section_key not in article["read_sections"]:
        article["read_sections"].append(section_key)
        
        article["section_details"].append({
            "section_type": section_type,
            "char_start": char_start,
            "read_at": datetime.now(timezone.utc).isoformat(),
            "extracted": extracted_items,
        })
        
        # Update total extractions
        for item_type, count in extracted_items.items():
            if item_type in article["total_extractions"]:
                article["total_extractions"][item_type] += count
    
    return reading_state


def get_article_provenance(article_id: str, reading_state: Dict) -> Dict:
    """
    Get the full provenance record for an article.
    
    Returns a dict showing exactly what was extracted from each section.
    """
    if article_id not in reading_state:
        return {"article_id": article_id, "status": "never_read", "sections": []}
    
    article = reading_state[article_id]
    return {
        "article_id": article_id,
        "first_read_at": article.get("first_read_at", "unknown"),
        "sections_read": len(article.get("read_sections", [])),
        "total_extractions": article.get("total_extractions", {}),
        "section_details": article.get("section_details", []),
    }


def get_unread_article_ids(reading_state: Dict, all_article_ids: List[str]) -> List[str]:
    """
    Find articles that still have unread sections.
    """
    unread = []
    for aid in all_article_ids:
        if aid not in reading_state:
            unread.append(aid)
        else:
            article = reading_state[aid]
            details = article.get("section_details", [])
            if len(details) < 5:  # Heuristic: most papers have 5+ sections
                unread.append(aid)
    
    return unread


def generate_provenance_report(reading_state: Dict) -> str:
    """
    Generate a human-readable provenance report for all articles.
    Used in the LaTeX appendix.
    """
    lines = []
    
    for article_id, data in reading_state.items():
        lines.append(f"\n\\subsection*{{{article_id}}}")
        lines.append(f"First read: {data.get('first_read_at', 'unknown')}")
        
        totals = data.get("total_extractions", {})
        lines.append(f"Total extractions: {totals.get('concepts', 0)} concepts, "
                     f"{totals.get('equations', 0)} equations, "
                     f"{totals.get('procedures', 0)} procedures, "
                     f"{totals.get('rules', 0)} rules")
        
        lines.append("\n\\begin{itemize}")
        for detail in data.get("section_details", []):
            section_type = detail.get("section_type", "unknown").replace("_", " ").title()
            extracted = detail.get("extracted", {})
            read_at = detail.get("read_at", "unknown")[:10]
            
            items_str = ", ".join(f"{v} {k}" for k, v in extracted.items() if v > 0)
            if items_str:
                lines.append(f"  \\item \\textbf{{{section_type}}} (read {read_at}): {items_str}")
            else:
                lines.append(f"  \\item \\textbf{{{section_type}}} (read {read_at}): no items extracted")
        lines.append("\\end{itemize}")
    
    return "\n".join(lines)
