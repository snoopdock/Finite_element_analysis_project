#!/usr/bin/env python3
"""
Evidence Orchestrator
Routes queries to all retrievers, merges results.
"""

import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict

from utils.text import clean_text
from research.arxiv_fulltext import search_arxiv
from research.wikipedia import search_wikipedia
from research.semantic_scholar import search_semantic_scholar
from research.archive_org import search_archive_org
from research.content_cache import cleanup_cache


def retrieve_evidence_parallel(queries: List[str], max_items: int = 6, max_workers: int = 4) -> List[Dict]:
    """Retrieve evidence from all sources in parallel."""
    cleanup_cache(max_size_kb=5000)

    evidence = []
    seen = set()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for q in queries:
            futures.append(executor.submit(search_arxiv, q, 2))
            futures.append(executor.submit(search_semantic_scholar, q, 2))
            futures.append(executor.submit(search_wikipedia, q, 2))

        for fut in as_completed(futures):
            try:
                for item in fut.result():
                    if item["source_id"] not in seen:
                        seen.add(item["source_id"])
                        evidence.append(item)
            except Exception as e:
                print(f"  [Evidence] Retrieval error: {e}", file=sys.stderr)

    return evidence[:max_items]


def get_smart_excerpt(source_item: Dict, max_chars: int = 3000) -> str:
    """Reads full text if available, otherwise falls back to abstract."""
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


def evidence_to_text(evidence: List[Dict], max_sources: int = 4, chars_per_source: int = 3000) -> str:
    """Convert evidence to text format for LLM consumption."""
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
    """Merge old and new evidence, keeping most recent."""
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
