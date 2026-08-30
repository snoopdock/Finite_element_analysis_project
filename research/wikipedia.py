#!/usr/bin/env python3
"""
Wikipedia Full Content Retriever
Fetches full page content via MediaWiki API.
"""

import re
import sys
import time
import requests
from datetime import datetime, timezone
from typing import List, Dict

from utils.text import clean_text
from research.content_cache import read_cache, write_cache, get_cache_path

USER_AGENT = (
    "FEA_Pipeline_Bot/1.0 "
    "(https://github.com/snoopdock/Finite_element_analysis_project; "
    "mailto:bot@example.com)"
)


def _clean_wikipedia_text(text: str) -> str:
    """Remove wiki markup and clean text."""
    text = re.sub(r'\[\[([^\]|]*\|)?([^\]]*)\]\]', r'\2', text)
    text = re.sub(r'\{\{[^}]*\}\}', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\[\d+\]', '', text)
    text = re.sub(r'\[\[Category:[^\]]*\]\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def search_wikipedia(query: str, max_results: int = 3) -> List[Dict]:
    """Search Wikipedia and fetch full page content."""
    search_url = "https://en.wikipedia.org/w/api.php"
    search_params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": max_results,
        "format": "json",
    }
    headers = {"User-Agent": USER_AGENT}

    try:
        resp = requests.get(search_url, params=search_params, headers=headers, timeout=30)
        resp.raise_for_status()
        search_data = resp.json()
    except Exception as e:
        print(f"  [Wikipedia] Search error: {e}", file=sys.stderr)
        return []

    sources = []
    results = search_data.get("query", {}).get("search", [])

    for result in results:
        try:
            title = result.get("title", "")
            source_id = "wiki_" + re.sub(r"[^a-zA-Z0-9_]+", "_", title.lower())[:60]

            cached_text = read_cache(source_id)
            if cached_text:
                full_text = cached_text
                status = "cached_full_text"
            else:
                page_url = "https://en.wikipedia.org/w/api.php"
                page_params = {
                    "action": "query",
                    "titles": title,
                    "prop": "extracts",
                    "explaintext": True,
                    "format": "json",
                }

                page_resp = requests.get(page_url, params=page_params, headers=headers, timeout=30)
                page_resp.raise_for_status()
                page_data = page_resp.json()

                pages = page_data.get("query", {}).get("pages", {})
                page = list(pages.values())[0] if pages else {}
                full_text = page.get("extract", "")
                full_text = _clean_wikipedia_text(full_text)

                if full_text:
                    write_cache(source_id, full_text)
                    status = "parsed_full_text"
                else:
                    status = "metadata_only"
                    full_text = ""

                time.sleep(1)

            page_url_link = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"

            sources.append({
                "source_id": source_id,
                "url": page_url_link,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "retriever_module": "research.wikipedia",
                "content_type": "text/html",
                "title": title,
                "authors": ["Wikipedia Contributors"],
                "metadata": {
                    "abstract": clean_text(result.get("snippet", ""), 500),
                    "word_count": len(full_text.split()) if full_text else 0,
                },
                "full_text_path": str(get_cache_path(source_id)) if full_text else None,
                "status": status,
            })

        except Exception as e:
            print(f"  [Wikipedia] Error processing '{title}': {e}", file=sys.stderr)
            continue

    return sources
