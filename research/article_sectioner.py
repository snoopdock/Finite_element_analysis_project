#!/usr/bin/env python3
"""
Article Sectioner - Splits raw article text into logical sections.
Tracks which sections have been read and which haven't.
"""

import re
from typing import List, Dict, Optional


# Common section headers found in academic papers
SECTION_PATTERNS = {
    "abstract": [
        r'^\s*abstract\s*$',
        r'^\s*summary\s*$',
    ],
    "introduction": [
        r'^\s*(?:\d+[\.\)]?\s*)?introduction\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?background\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?overview\s*$',
    ],
    "literature_review": [
        r'^\s*(?:\d+[\.\)]?\s*)?literature\s*review\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?related\s*work\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?previous\s*work\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?state\s*of\s*the\s*art\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?prior\s*work\s*$',
    ],
    "methodology": [
        r'^\s*(?:\d+[\.\)]?\s*)?method(?:ology|s)?\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?approach\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?proposed\s*(?:method|approach|framework)\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?formulation\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?mathematical\s*formulation\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?numerical\s*(?:method|formulation|approach)\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?theoretical\s*(?:framework|background)\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?finite\s*element\s*(?:formulation|method|procedure)\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?weak\s*form(?:ulation)?\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?galerkin\s*(?:method|formulation|approximation)\s*$',
    ],
    "results": [
        r'^\s*(?:\d+[\.\)]?\s*)?results?\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?numerical\s*results?\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?experiments?\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?computational\s*results?\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?case\s*studies?\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?numerical\s*examples?\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?validation\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?verification\s*$',
    ],
    "discussion": [
        r'^\s*(?:\d+[\.\)]?\s*)?discussion\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?analysis\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?comparison\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?sensitivity\s*analysis\s*$',
    ],
    "conclusion": [
        r'^\s*(?:\d+[\.\)]?\s*)?conclusions?\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?summary\s*and\s*conclusions?\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?concluding\s*remarks?\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?future\s*work\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?outlook\s*$',
    ],
    "references": [
        r'^\s*(?:\d+[\.\)]?\s*)?references?\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?bibliography\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?citations?\s*$',
    ],
    "appendix": [
        r'^\s*(?:\d+[\.\)]?\s*)?appendix\s*$',
        r'^\s*(?:\d+[\.\)]?\s*)?supplementary\s*(?:material|information)\s*$',
    ],
}


def split_article_into_sections(text: str) -> List[Dict]:
    """
    Split raw article text into logical sections.
    
    Returns:
        List of dicts: [{"section_type": "methodology", "content": "...", "char_start": 0, "char_end": 500}, ...]
    """
    if not text or not text.strip():
        return [{"section_type": "unknown", "content": text, "char_start": 0, "char_end": len(text)}]
    
    lines = text.split('\n')
    sections = []
    current_section = {"section_type": "preamble", "content": "", "char_start": 0}
    current_char = 0
    
    for line in lines:
        line_stripped = line.strip()
        detected_type = _detect_section_type(line_stripped)
        
        if detected_type:
            # Save the current section
            if current_section["content"].strip():
                current_section["char_end"] = current_char
                sections.append(current_section)
            
            # Start a new section
            current_section = {
                "section_type": detected_type,
                "content": "",
                "char_start": current_char,
            }
        else:
            current_section["content"] += line + "\n"
        
        current_char += len(line) + 1  # +1 for the newline
    
    # Don't forget the last section
    if current_section["content"].strip():
        current_section["char_end"] = current_char
        sections.append(current_section)
    
    # If no sections were detected, return the whole text as "unknown"
    if not sections:
        return [{"section_type": "unknown", "content": text, "char_start": 0, "char_end": len(text)}]
    
    return sections


def _detect_section_type(line: str) -> Optional[str]:
    """Check if a line matches any known section header pattern."""
    if not line or len(line) > 100:  # Section headers are usually short
        return None
    
    line_lower = line.lower().strip()
    
    for section_type, patterns in SECTION_PATTERNS.items():
        for pattern in patterns:
            if re.match(pattern, line_lower, re.IGNORECASE):
                return section_type
    
    return None


def get_unread_sections(article_id: str, sections: List[Dict], reading_state: Dict) -> List[Dict]:
    """
    Filter out sections that have already been read.
    
    Args:
        article_id: Unique identifier for the article
        sections: List of section dicts from split_article_into_sections
        reading_state: Dict tracking which sections have been read
        
    Returns:
        List of sections that haven't been read yet
    """
    article_state = reading_state.get(article_id, {})
    read_sections = set(article_state.get("read_sections", []))
    
    unread = []
    for section in sections:
        section_key = f"{section['section_type']}_{section['char_start']}"
        if section_key not in read_sections:
            unread.append(section)
    
    return unread


def get_reading_progress(article_id: str, sections: List[Dict], reading_state: Dict) -> Dict:
    """
    Get a summary of how much of an article has been read.
    
    Returns:
        Dict with reading progress stats
    """
    article_state = reading_state.get(article_id, {})
    read_sections = set(article_state.get("read_sections", []))
    
    total_chars = len(''.join(s.get("content", "") for s in sections))
    read_chars = sum(
        len(s.get("content", "")) for s in sections
        if f"{s['section_type']}_{s['char_start']}" in read_sections
    )
    
    return {
        "article_id": article_id,
        "total_sections": len(sections),
        "read_sections": len(read_sections),
        "unread_sections": len(sections) - len(read_sections),
        "total_chars": total_chars,
        "read_chars": read_chars,
        "coverage_percent": round((read_chars / total_chars * 100) if total_chars > 0 else 0, 1),
    }
