#!/usr/bin/env python3
"""Evidence retrieval, provenance, section-aware reading, and merging."""

from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from utils.text import clean_text
from research.arxiv_fulltext import search_arxiv
from research.wikipedia import search_wikipedia
from research.semantic_scholar import search_semantic_scholar, get_last_retrieval_status
from research.content_cache import cleanup_cache
from research.article_sectioner import split_article_into_sections, get_unread_sections
from research.reading_tracker import mark_section_read
from research.ranking import rank_items_for_queries
from research.diversity import select_diverse_evidence


_LAST_RETRIEVAL_REPORT: Dict = {
    "status": "not_run",
    "providers": {},
    "returned_records": 0,
    "selected_records": 0,
}


def _aggregate_provider_status(statuses: List[str]) -> str:
    """Aggregate per-query provider outcomes without hiding partial failures."""
    normalized = [str(status).strip() for status in statuses if str(status).strip()]
    if not normalized:
        return "unknown"
    if all(status == "success" for status in normalized):
        return "success"
    if all(status == "empty_result" for status in normalized):
        return "empty_result"
    if all(status == "rate_limited" for status in normalized):
        return "rate_limited"
    if any(status == "success" for status in normalized):
        return "partial_failure"
    if any(status in {"network_error", "server_error", "client_error", "http_error", "invalid_response"} for status in normalized):
        return "failure"
    return "mixed"


def _run_provider_search(
    provider_name: str,
    search_fn: Callable,
    query: str,
    max_results: int,
) -> tuple:
    """Run one provider search and return both records and its worker-local status."""
    try:
        results = search_fn(query, max_results)
    except Exception as exc:
        return [], {"status": "exception", "error": str(exc)}

    if provider_name == "semantic_scholar":
        status = get_last_retrieval_status()
        if isinstance(status, dict) and status:
            return results if isinstance(results, list) else [], dict(status)

    if isinstance(results, list):
        return results, {
            "status": "success" if results else "empty_result",
            "returned_records": len(results),
        }

    return [], {"status": "invalid_result_type"}


def get_last_retrieval_report() -> Dict:
    """Return a copy of the latest retrieval-cycle report."""
    return dict(_LAST_RETRIEVAL_REPORT)


def retrieve_evidence_parallel(
    queries: List[str],
    max_items: int = 4,
    max_workers: int = 3,
    max_per_provider: int = 2,
    max_per_source_type: int = 3,
) -> List[Dict]:
    """Retrieve evidence while preserving provenance and configured diversity caps."""
    global _LAST_RETRIEVAL_REPORT

    cleanup_cache()

    normalized_queries = [
        str(query).strip()
        for query in queries or []
        if str(query).strip()
    ]

    retrieval_timestamp = datetime.now(timezone.utc).isoformat()
    _LAST_RETRIEVAL_REPORT = {
        "status": "not_run",
        "retrieved_at": retrieval_timestamp,
        "query_count": len(normalized_queries),
        "providers": {},
        "returned_records": 0,
        "selected_records": 0,
    }

    if not normalized_queries:
        _LAST_RETRIEVAL_REPORT["status"] = "empty_query_set"
        return []

    provider_specs = {
        "arxiv": (search_arxiv, "preprint"),
        "semantic_scholar": (search_semantic_scholar, "academic"),
        "wikipedia": (search_wikipedia, "wikipedia"),
    }

    futures = {}
    provider_attempts: Dict[str, List[Dict]] = {
        provider_name: [] for provider_name in provider_specs
    }

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for query in normalized_queries:
            for provider_name, (search_fn, source_type) in provider_specs.items():
                futures[executor.submit(
                    _run_provider_search,
                    provider_name,
                    search_fn,
                    query,
                    2,
                )] = (provider_name, query, source_type)

        candidates_by_id: Dict[str, Dict] = {}

        for future in as_completed(futures):
            provider_name, query, source_type = futures[future]
            try:
                results, outcome = future.result()
            except Exception as exc:
                results = []
                outcome = {"status": "exception", "error": str(exc)}
                print(
                    f"  [Evidence] {provider_name} retrieval error for '{query}': {exc}",
                    file=sys.stderr,
                )

            outcome = dict(outcome) if isinstance(outcome, dict) else {"status": "unknown"}
            outcome["query"] = query
            outcome["provider"] = provider_name
            outcome["returned_records"] = len(results) if isinstance(results, list) else 0
            provider_attempts[provider_name].append(outcome)

            if not isinstance(results, list):
                continue

            for item in results:
                if not isinstance(item, dict):
                    continue
                source_id = item.get("source_id")
                if not source_id:
                    continue
                source_id = str(source_id)

                existing = candidates_by_id.get(source_id)
                if existing is None:
                    enriched = dict(item)
                    enriched["source_id"] = source_id
                    enriched["provider"] = provider_name
                    enriched["source_type"] = source_type
                    enriched["query_context"] = query
                    enriched["query_contexts"] = [query]
                    enriched["provider_names"] = [provider_name]
                    enriched["source_types"] = [source_type]
                    enriched["retrieved_at"] = retrieval_timestamp
                    candidates_by_id[source_id] = enriched
                    continue

                query_contexts = existing.setdefault("query_contexts", [])
                if query not in query_contexts:
                    query_contexts.append(query)
                providers = existing.setdefault("provider_names", [])
                if provider_name not in providers:
                    providers.append(provider_name)
                source_types = existing.setdefault("source_types", [])
                if source_type not in source_types:
                    source_types.append(source_type)
                existing.setdefault("query_context", query)

                old_full_text = bool(
                    existing.get("full_text_path") and os.path.exists(existing.get("full_text_path"))
                )
                new_full_text = bool(
                    item.get("full_text_path") and os.path.exists(item.get("full_text_path"))
                )
                if new_full_text and not old_full_text:
                    for key in ("url", "content_type", "full_text_path", "status", "metadata"):
                        if key in item:
                            existing[key] = item[key]

    candidates = list(candidates_by_id.values())
    for item in candidates:
        item["query_contexts"] = sorted(set(item.get("query_contexts", [])))
        item["provider_names"] = sorted(set(item.get("provider_names", [])))
        item["source_types"] = sorted(set(item.get("source_types", [])))

    ranked = rank_items_for_queries(normalized_queries, candidates, top_k=len(candidates))
    selected = select_diverse_evidence(
        ranked,
        max_items=max(0, int(max_items)),
        max_per_provider=max(0, int(max_per_provider)),
        max_per_source_type=max(0, int(max_per_source_type)),
    )

    provider_reports = {}
    for provider_name, attempts in provider_attempts.items():
        statuses = [str(item.get("status", "unknown")) for item in attempts]
        provider_reports[provider_name] = {
            "status": _aggregate_provider_status(statuses),
            "attempts": sorted(attempts, key=lambda item: str(item.get("query", ""))),
            "queries_attempted": len(attempts),
            "returned_records": sum(int(item.get("returned_records", 0) or 0) for item in attempts),
        }

    successful_providers = sum(
        1 for report in provider_reports.values()
        if report.get("status") == "success"
    )
    failed_providers = sum(
        1 for report in provider_reports.values()
        if report.get("status") in {"rate_limited", "failure", "partial_failure", "mixed", "exception"}
    )

    if successful_providers and failed_providers:
        cycle_status = "partial_failure"
    elif successful_providers:
        cycle_status = "success"
    elif failed_providers:
        cycle_status = "failure"
    else:
        cycle_status = "empty_result"

    _LAST_RETRIEVAL_REPORT = {
        "status": cycle_status,
        "retrieved_at": retrieval_timestamp,
        "query_count": len(normalized_queries),
        "providers": provider_reports,
        "returned_records": len(candidates),
        "selected_records": len(selected),
    }

    cleanup_cache()
    return selected


def get_next_unread_content(source_item: Dict, reading_state: Dict, max_chars: int = 3000) -> Optional[Dict]:
    """Return the next unread full-text section of an article."""
    full_text_path = source_item.get("full_text_path")
    article_id = str(source_item.get("source_id", "unknown"))
    if not full_text_path or not os.path.exists(full_text_path):
        return None
    try:
        with open(full_text_path, "r", encoding="utf-8") as handle:
            full_text = handle.read()
    except OSError:
        return None
    if not full_text.strip():
        return None
    sections = split_article_into_sections(full_text)
    unread = get_unread_sections(article_id, sections, reading_state)
    if not unread:
        return None
    next_section = unread[0]
    content = str(next_section.get("content", ""))[:max_chars]
    return {
        "section_type": next_section.get("section_type", "unknown"),
        "content": content,
        "char_start": next_section.get("char_start", 0),
        "char_end": next_section.get("char_end", next_section.get("char_start", 0) + len(content)),
    }


def get_smart_excerpt(source_item: Dict, max_chars: int = 3000) -> str:
    """Legacy full-text excerpt helper."""
    full_text_path = source_item.get("full_text_path")
    if full_text_path and os.path.exists(full_text_path):
        try:
            with open(full_text_path, "r", encoding="utf-8") as handle:
                text = handle.read()
            if len(text) > max_chars:
                snippet = text[:max_chars]
                last_para = snippet.rfind("\n\n")
                if last_para > max_chars * 0.5:
                    snippet = snippet[:last_para]
                return snippet + "\n[... text truncated ...]"
            return text
        except OSError:
            pass
    return "No full text available."


def evidence_to_text_section_aware(evidence: List[Dict], reading_state: Dict, max_sources: int = 4, chars_per_source: int = 3000) -> tuple:
    """Select the next unread full-text section from ranked evidence."""
    blocks = []
    sections_read_this_cycle = []
    updated_state = reading_state
    count = 0
    for item in evidence:
        if count >= max_sources or not isinstance(item, dict):
            continue
        article_id = str(item.get("source_id", "unknown"))
        next_content = get_next_unread_content(item, updated_state, chars_per_source)
        if next_content is None:
            continue
        section_type = next_content["section_type"]
        content = next_content["content"]
        char_start = next_content["char_start"]
        char_end = next_content["char_end"]
        blocks.append(
            f'<source id="{article_id}" title="{clean_text(item.get("title", ""), 200)}" '
            f'section="{clean_text(str(section_type), 100)}" status="{clean_text(str(item.get("status", "unknown")), 50)}">\n'
            f'{clean_text(content, chars_per_source)}\n</source>'
        )
        sections_read_this_cycle.append({
            "article_id": article_id,
            "section_type": section_type,
            "char_start": char_start,
            "char_end": char_end,
        })
        count += 1
    return "\n\n".join(blocks), updated_state, sections_read_this_cycle


def evidence_to_text(evidence: List[Dict], max_sources: int = 4, chars_per_source: int = 3000) -> str:
    """Legacy full-text formatter retained for compatibility."""
    blocks = []
    for item in evidence[:max_sources]:
        excerpt = get_smart_excerpt(item, max_chars=chars_per_source)
        if excerpt == "No full text available.":
            continue
        blocks.append(
            '<source id="' + str(item.get("source_id", "unknown")) + '" title="' +
            clean_text(item.get("title", ""), 200) + '" status="' + str(item.get("status", "")) + '">\n' +
            clean_text(excerpt, chars_per_source) + "\n</source>"
        )
    return "\n\n".join(blocks)


def merge_evidence(old: List[Dict], new: List[Dict], max_keep: int = 200) -> List[Dict]:
    """Merge evidence by source_id while retaining provenance and current ranking."""
    merged = {}
    for item in old or []:
        if isinstance(item, dict) and item.get("source_id"):
            merged[str(item["source_id"])] = dict(item)

    for item in new or []:
        if not (isinstance(item, dict) and item.get("source_id")):
            continue
        source_id = str(item["source_id"])
        if source_id not in merged:
            merged[source_id] = dict(item)
            continue
        existing = merged[source_id]
        for key in ("query_contexts", "provider_names", "source_types"):
            old_values = existing.get(key, [])
            new_values = item.get(key, [])
            if isinstance(old_values, str):
                old_values = [old_values]
            if isinstance(new_values, str):
                new_values = [new_values]
            if not isinstance(old_values, list):
                old_values = []
            if not isinstance(new_values, list):
                new_values = []
            existing[key] = sorted(set(old_values) | set(new_values))
        for key in ("title", "authors", "url", "metadata", "full_text_path", "status", "content_type", "ranking"):
            if key in item:
                existing[key] = item[key]
        if item.get("query_context"):
            existing["query_context"] = item["query_context"]
        if item.get("retrieved_at"):
            existing["retrieved_at"] = item["retrieved_at"]

    values = list(merged.values())
    values.sort(
        key=lambda item: (
            -float(item.get("ranking", {}).get("score", 0.0)),
            str(item.get("source_id", "")),
        )
    )
    return values[:max(0, int(max_keep))]


def merge_knowledge(existing_kb: Dict, new_extraction: Dict) -> Dict:
    """Merge extracted knowledge while retaining all known source IDs."""
    if not isinstance(new_extraction, dict):
        return existing_kb or {}
    kb = dict(existing_kb) if isinstance(existing_kb, dict) else {}
    for category in ("concepts", "procedures", "equations", "rules"):
        existing = kb.get(category, [])
        if not isinstance(existing, list):
            existing = []
        new_items = new_extraction.get(category, [])
        if not isinstance(new_items, list):
            kb[category] = existing
            continue
        existing_index = {}
        for item in existing:
            if not isinstance(item, dict):
                continue
            key = str(item.get("name") or item.get("title") or item.get("rule") or "").lower().strip()
            if key:
                existing_index[key] = item
        for new_item in new_items:
            if not isinstance(new_item, dict):
                continue
            key = str(new_item.get("name") or new_item.get("title") or new_item.get("rule") or "").lower().strip()
            new_sources = new_item.get("source_ids", [])
            if not isinstance(new_sources, list):
                new_sources = []
            if not key:
                existing.append(new_item)
                continue
            if key in existing_index:
                old_item = existing_index[key]
                old_sources = old_item.get("source_ids", [])
                if not isinstance(old_sources, list):
                    old_sources = []
                old_item["source_ids"] = sorted(set(old_sources) | set(new_sources))
                old_explanation = str(old_item.get("explanation", ""))
                new_explanation = str(new_item.get("explanation", ""))
                if len(new_explanation) > len(old_explanation):
                    old_item["explanation"] = new_explanation
            else:
                existing.append(new_item)
                existing_index[key] = new_item
        kb[category] = existing
    return kb


def confirm_sections_read(sections_read: List[Dict], extracted_items: Dict[str, Dict[str, int]], reading_state: Dict) -> Dict:
    """Confirm sections only after successful attributable extraction."""
    for section_info in sections_read or []:
        if not isinstance(section_info, dict):
            continue
        article_id = section_info.get("article_id")
        if not article_id:
            continue
        items = (extracted_items or {}).get(article_id, {"concepts": 0, "equations": 0, "procedures": 0, "rules": 0})
        reading_state = mark_section_read(
            article_id=str(article_id),
            section_type=section_info.get("section_type", "unknown"),
            char_start=section_info.get("char_start", 0),
            extracted_items=items,
            reading_state=reading_state,
        )
    return reading_state


def get_articles_needing_more_reading(evidence: List[Dict], reading_state: Dict, min_unread_sections: int = 1) -> List[str]:
    needs_reading = []
    for item in evidence or []:
        if not isinstance(item, dict):
            continue
        article_id = str(item.get("source_id", "unknown"))
        full_text_path = item.get("full_text_path")
        if not full_text_path or not os.path.exists(full_text_path):
            continue
        try:
            with open(full_text_path, "r", encoding="utf-8") as handle:
                full_text = handle.read()
        except OSError:
            continue
        sections = split_article_into_sections(full_text)
        unread = get_unread_sections(article_id, sections, reading_state)
        if len(unread) >= min_unread_sections:
            needs_reading.append(article_id)
    return needs_reading


def get_reading_summary(evidence: List[Dict], reading_state: Dict) -> Dict:
    """Return section-level reading coverage."""
    total_articles = len(evidence or [])
    fully_read = 0
    partially_read = 0
    never_read = 0
    previously_read_cache_missing = 0
    total_sections_read = 0
    total_sections_available = 0
    for item in evidence or []:
        if not isinstance(item, dict):
            continue
        article_id = str(item.get("source_id", "unknown"))
        full_text_path = item.get("full_text_path")
        article_history = reading_state.get(article_id, {}) if isinstance(reading_state, dict) else {}
        previously_read = bool(isinstance(article_history, dict) and article_history.get("read_sections"))
        if not full_text_path or not os.path.exists(full_text_path):
            if previously_read:
                previously_read_cache_missing += 1
            else:
                never_read += 1
            continue
        try:
            with open(full_text_path, "r", encoding="utf-8") as handle:
                full_text = handle.read()
        except OSError:
            if previously_read:
                previously_read_cache_missing += 1
            else:
                never_read += 1
            continue
        sections = split_article_into_sections(full_text)
        unread = get_unread_sections(article_id, sections, reading_state)
        available = len(sections)
        read_count = max(0, available - len(unread))
        total_sections_available += available
        total_sections_read += read_count
        if len(unread) == 0:
            fully_read += 1
        elif read_count > 0:
            partially_read += 1
        else:
            never_read += 1
    coverage = total_sections_read / total_sections_available * 100.0 if total_sections_available > 0 else 0.0
    return {
        "total_articles": total_articles,
        "fully_read": fully_read,
        "partially_read": partially_read,
        "never_read": never_read,
        "previously_read_cache_missing": previously_read_cache_missing,
        "total_sections_read": total_sections_read,
        "total_sections_available": total_sections_available,
        "reading_coverage_percent": round(coverage, 1),
    }
