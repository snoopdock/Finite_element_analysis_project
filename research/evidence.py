#!/usr/bin/env python3
"""
Evidence management, retrieval, and merging with section-aware reading and provenance tracking.
"""

import os
import sys
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from utils.text import clean_text
from research.arxiv_fulltext import search_arxiv
from research.wikipedia import search_wikipedia
from research.semantic_scholar import search_semantic_scholar
from research.archive_org import search_archive_org
from research.content_cache import cleanup_cache
from research.article_sectioner import split_article_into_sections, get_unread_sections
from research.reading_tracker import load_reading_state, save_reading_state, mark_section_read


def retrieve_evidence_parallel(queries: List[str], max_items: int = 4, max_workers: int = 3) -> List[Dict]:
    """
    Retrieve evidence from all sources in parallel with full provenance metadata.
    """
    cleanup_cache(max_size_kb=5000)

    evidence = []
    seen = set()
    retrieval_timestamp = datetime.now(timezone.utc).isoformat()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for q in queries:
            futures.append(executor.submit(search_arxiv, q, 2))
            futures.append(executor.submit(search_semantic_scholar, q, 2))
            futures.append(executor.submit(search_wikipedia, q, 2))
            # Uncomment when Archive.org integration is ready:
            # futures.append(executor.submit(search_archive_org, q, 1))

        for fut in as_completed(futures):
            try:
                for item in fut.result():
                    if item["source_id"] not in seen:
                        seen.add(item["source_id"])
                        # Stamp retrieval provenance
                        item["retrieved_at"] = retrieval_timestamp
                        item["query_context"] = queries[0] if queries else "unknown"
                        evidence.append(item)
            except Exception as e:
                print(f"  [Evidence] Retrieval error: {e}", file=sys.stderr)

    return evidence[:max_items]


def get_next_unread_content(source_item: Dict, reading_state: Dict, max_chars: int = 3000) -> Optional[Dict]:
    """
    Get the next unread section of an article instead of just the first 3000 chars.
    This ensures no article is thrown away after a single read.
    
    Args:
        source_item: The evidence dict for this source
        reading_state: The current reading state tracking what has been read
        max_chars: Maximum characters to return for this section
        
    Returns:
        Dict with section content, type, and position, or None if fully read.
    """
    full_text_path = source_item.get("full_text_path")
    article_id = source_item.get("source_id", "unknown")
    
    if not full_text_path or not os.path.exists(full_text_path):
        # Fallback to abstract if no cached text exists
        abstract = source_item.get("metadata", {}).get("abstract", "")
        if abstract:
            return {
                "section_type": "abstract",
                "content": abstract[:max_chars],
                "char_start": 0,
                "char_end": len(abstract[:max_chars]),
            }
        return None
    
    with open(full_text_path, "r", encoding="utf-8") as f:
        full_text = f.read()
    
    if not full_text or not full_text.strip():
        return None
    
    # Split the article into logical sections
    sections = split_article_into_sections(full_text)
    
    # Get only the sections that haven't been read yet
    unread = get_unread_sections(article_id, sections, reading_state)
    
    if not unread:
        return None  # Article has been fully read
    
    # Return the first unread section (truncated to max_chars for the LLM)
    next_section = unread[0]
    content = next_section["content"][:max_chars]
    
    return {
        "section_type": next_section["section_type"],
        "content": content,
        "char_start": next_section["char_start"],
        "char_end": next_section.get("char_end", next_section["char_start"] + len(content)),
    }


def get_smart_excerpt(source_item: Dict, max_chars: int = 3000) -> str:
    """
    Legacy function: Reads full text if available, otherwise falls back to abstract.
    Use get_next_unread_content() for section-aware reading.
    """
    full_text_path = source_item.get("full_text_path")

    if full_text_path and os.path.exists(full_text_path):
        try:
            with open(full_text_path, "r", encoding="utf-8") as f:
                text = f.read()
            if len(text) > max_chars:
                snippet = text[:max_chars]
                last_para = snippet.rfind("\n\n")
                if last_para > max_chars * 0.5:
                    snippet = snippet[:last_para]
                return snippet + "\n[... text truncated ...]"
            return text
        except Exception:
            pass

    return source_item.get("metadata", {}).get("abstract", "No text available.")


def evidence_to_text_section_aware(
    evidence: List[Dict],
    reading_state: Dict,
    max_sources: int = 4,
    chars_per_source: int = 3000
) -> tuple:
    """
    Convert evidence to text format for LLM consumption using section-aware reading.
    Reads the next unread section of each article instead of always reading the beginning.
    
    Args:
        evidence: List of evidence dicts
        reading_state: Current reading state
        max_sources: Maximum number of sources to process
        chars_per_source: Max characters per source
        
    Returns:
        Tuple of (text_for_llm, updated_reading_state, sections_read_this_cycle)
    """
    blocks = []
    sections_read_this_cycle = []
    updated_state = reading_state
    
    for item in evidence[-max_sources:]:
        article_id = item.get("source_id", "unknown")
        
        # Try to get the next unread section
        next_content = get_next_unread_content(item, updated_state, chars_per_source)
        
        if next_content is None:
            # Article fully read or no content available
            continue
        
        section_type = next_content["section_type"]
        content = next_content["content"]
        char_start = next_content["char_start"]
        char_end = next_content["char_end"]
        
        # Build the text block for the LLM
        block = (
            f'<source id="{article_id}" '
            f'title="{clean_text(item.get("title", ""), 200)}" '
            f'section="{section_type}" '
            f'status="{item.get("status", "unknown")}">\n'
            f'{clean_text(content, chars_per_source)}\n'
            f'</source>'
        )
        blocks.append(block)
        
        # Record what we're about to read (will be confirmed after extraction)
        sections_read_this_cycle.append({
            "article_id": article_id,
            "section_type": section_type,
            "char_start": char_start,
            "char_end": char_end,
        })
    
    text = "\n\n".join(blocks)
    return text, updated_state, sections_read_this_cycle


def evidence_to_text(evidence: List[Dict], max_sources: int = 4, chars_per_source: int = 3000) -> str:
    """
    Legacy function: Convert evidence to text format for LLM consumption.
    Kept for backward compatibility. Use evidence_to_text_section_aware() for new code.
    """
    blocks = []
    for item in evidence[-max_sources:]:
        excerpt = get_smart_excerpt(item, max_chars=chars_per_source)
        block = (
            '<source id="' + item.get("source_id", "unknown") + '" title="' +
            clean_text(item.get("title", ""), 200) + '" status="' + item.get("status", "") + '">\n' +
            clean_text(excerpt, chars_per_source) +
            "\n</source>"
        )
        blocks.append(block)
    return "\n\n".join(blocks)


def merge_evidence(old: List[Dict], new: List[Dict], max_keep: int = 200) -> List[Dict]:
    """Merge old and new evidence, keeping most recent. Preserves provenance metadata."""
    merged = {}
    for item in old:
        if isinstance(item, dict) and item.get("source_id"):
            merged[item["source_id"]] = item
    for item in new:
        if isinstance(item, dict) and item.get("source_id"):
            merged[item["source_id"]] = item
    return list(merged.values())[-max_keep:]


def merge_knowledge(existing_kb: Dict, new_extraction: Dict) -> Dict:
    """Merge new extraction into existing knowledge base."""
    if not isinstance(new_extraction, dict):
        return existing_kb

    kb = dict(existing_kb) if existing_kb else {}

    for category in ["concepts", "procedures", "equations", "rules"]:
        existing = kb.get(category, [])
        new_items = new_extraction.get(category, [])
        if not isinstance(new_items, list):
            continue

        existing_index = {}
        for item in existing:
            if isinstance(item, dict):
                key = (item.get("name") or item.get("title") or item.get("rule") or "").lower().strip()
                if key:
                    existing_index[key] = item

        for new_item in new_items:
            if not isinstance(new_item, dict):
                continue
            key = (new_item.get("name") or new_item.get("title") or new_item.get("rule") or "").lower().strip()

            if not key:
                existing.append(new_item)
            elif key in existing_index:
                old_item = existing_index[key]
                old_item["source_ids"] = sorted(list(
                    set(old_item.get("source_ids", [])) | set(new_item.get("source_ids", []))
                ))
                if len(new_item.get("explanation", "")) > len(old_item.get("explanation", "")):
                    old_item["explanation"] = new_item["explanation"]
            else:
                existing.append(new_item)
                existing_index[key] = new_item

        kb[category] = existing

    return kb


def confirm_sections_read(
    sections_read: List[Dict],
    extracted_items: Dict[str, Dict[str, int]],
    reading_state: Dict
) -> Dict:
    """
    Confirm that sections were successfully read and record what was extracted.
    Call this after the LLM extraction phase completes.
    
    Args:
        sections_read: List of sections that were read this cycle
        extracted_items: Dict mapping article_id to what was extracted,
                         e.g. {"arxiv_123": {"concepts": 3, "equations": 2}}
        reading_state: Current reading state
        
    Returns:
        Updated reading state
    """
    for section_info in sections_read:
        article_id = section_info["article_id"]
        section_type = section_info["section_type"]
        char_start = section_info["char_start"]
        
        # Get what was extracted from this article
        items = extracted_items.get(article_id, {"concepts": 0, "equations": 0, "procedures": 0, "rules": 0})
        
        reading_state = mark_section_read(
            article_id=article_id,
            section_type=section_type,
            char_start=char_start,
            extracted_items=items,
            reading_state=reading_state
        )
    
    return reading_state


def get_articles_needing_more_reading(
    evidence: List[Dict],
    reading_state: Dict,
    min_unread_sections: int = 1
) -> List[str]:
    """
    Find articles that still have unread sections.
    These articles should be prioritized in the next Extract phase.
    
    Args:
        evidence: List of all evidence dicts
        reading_state: Current reading state
        min_unread_sections: Minimum number of unread sections to qualify
        
    Returns:
        List of article IDs that need more reading
    """
    needs_reading = []
    
    for item in evidence:
        article_id = item.get("source_id", "unknown")
        full_text_path = item.get("full_text_path")
        
        if not full_text_path or not os.path.exists(full_text_path):
            continue
        
        try:
            with open(full_text_path, "r", encoding="utf-8") as f:
                full_text = f.read()
        except Exception:
            continue
        
        sections = split_article_into_sections(full_text)
        unread = get_unread_sections(article_id, sections, reading_state)
        
        if len(unread) >= min_unread_sections:
            needs_reading.append(article_id)
    
    return needs_reading


def get_reading_summary(evidence: List[Dict], reading_state: Dict) -> Dict:
    """
    Get a summary of reading progress across all articles.
    Useful for the convergence check and validation reports.
    
    Returns:
        Dict with overall reading statistics
    """
    total_articles = len(evidence)
    fully_read = 0
    partially_read = 0
    never_read = 0
    total_sections_read = 0
    total_sections_available = 0
    
    for item in evidence:
        article_id = item.get("source_id", "unknown")
        full_text_path = item.get("full_text_path")
        
        if not full_text_path or not os.path.exists(full_text_path):
            never_read += 1
            continue
        
        try:
            with open(full_text_path, "r", encoding="utf-8") as f:
                full_text = f.read()
        except Exception:
            never_read += 1
            continue
        
        sections = split_article_into_sections(full_text)
        unread = get_unread_sections(article_id, sections, reading_state)
        
        total_sections_available += len(sections)
        total_sections_read += len(sections) - len(unread)
        
        if len(unread) == 0:
            fully_read += 1
        elif article_id in reading_state:
            partially_read += 1
        else:
            never_read += 1
    
    return {
        "total_articles": total_articles,
        "fully_read": fully_read,
        "partially_read": partially_read,
        "never_read": never_read,
        "total_sections_read": total_sections_read,
        "total_sections_available": total_sections_available,
        "reading_coverage_percent": round(
            (total_sections_read / total_sections_available * 100)
            if total_sections_available > 0 else 0, 1
        ),
    }
