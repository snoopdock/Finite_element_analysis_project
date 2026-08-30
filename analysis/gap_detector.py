#!/usr/bin/env python3
"""Information type classifier for knowledge base entries."""

from typing import Dict, List, Optional


def classify_knowledge_type(concept_text: str, source_count: int) -> str:
    """
    Classify a piece of knowledge into one of 4 types.
    
    Types:
    - general: Textbook-level facts (appears in many sources)
    - attributed: Specific claims from one source
    - novel: Original contribution unique to the paper
    - synthesized: Combined from multiple sources
    
    Args:
        concept_text: The text content to classify
        source_count: Number of sources that mention this concept
        
    Returns:
        str: One of "general", "attributed", "novel", "synthesized"
    """
    text_lower = concept_text.lower()
    
    # If concept appears in 3+ sources, it's general knowledge
    if source_count >= 3:
        return "general"
    
    # Novel contribution indicators
    novel_indicators = [
        "we propose", "we introduce", "our method", "we present",
        "we develop", "our results", "we demonstrate", "our contribution",
        "in this paper", "we show that", "our approach", "novel",
        "first time", "new method", "we derive", "we prove"
    ]
    
    for indicator in novel_indicators:
        if indicator in text_lower:
            return "novel"
    
    # Attributed knowledge indicators
    attributed_indicators = [
        "as shown by", "as demonstrated by", "according to",
        "as established by", "as proven by", "following the work of",
        "based on the work of", "as described in", "et al."
    ]
    
    for indicator in attributed_indicators:
        if indicator in text_lower:
            return "attributed"
    
    # If it comes from exactly one source, it's likely attributed or novel
    if source_count == 1:
        return "attributed"
    
    # Multiple sources but not enough for general = synthesized
    if source_count == 2:
        return "synthesized"
    
    return "general"


def get_type_description(info_type: str) -> str:
    """Get a human-readable description of the information type."""
    descriptions = {
        "general": "General knowledge: textbook-level fact common across FEM literature.",
        "attributed": "Attributed knowledge: specific claim borrowed from cited work.",
        "novel": "Novel contribution: original result unique to this source.",
        "synthesized": "Synthesized knowledge: derived by combining multiple sources."
    }
    return descriptions.get(info_type, "Unclassified knowledge.")


def get_type_latex_label(info_type: str) -> str:
    """Get a LaTeX-formatted label for the information type."""
    labels = {
        "general": r"\textit{[General]}",
        "attributed": r"\textbf{[Attributed]}",
        "novel": r"\textsc{[Novel]}",
        "synthesized": r"\textsf{[Synthesized]}"
    }
    return labels.get(info_type, r"\textit{[Unclassified]}")
