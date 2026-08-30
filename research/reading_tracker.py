#!/usr/bin/env python3
"""
Reading Tracker.

Tracks:
- which sections of each article were read
- when they were read
- what knowledge was extracted from them
"""

import json
import os
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List


TRACKER_FILE = Path(
    "state/reading_state.json"
)


def _utcnow():
    return datetime.now(
        timezone.utc
    ).isoformat()


def load_reading_state() -> Dict:
    """Load reading state from disk."""

    if not TRACKER_FILE.exists():
        return {}

    try:
        with open(
            TRACKER_FILE,
            "r",
            encoding="utf-8",
        ) as handle:
            data = json.load(
                handle
            )

    except (
        OSError,
        json.JSONDecodeError,
    ):
        return {}

    if not isinstance(
        data,
        dict,
    ):
        return {}

    return data


def save_reading_state(
    state: Dict,
):
    """Atomically save reading state."""

    if not isinstance(
        state,
        dict,
    ):
        raise TypeError(
            "reading state must be a dictionary"
        )

    TRACKER_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, tmp_path = tempfile.mkstemp(
        dir=TRACKER_FILE.parent,
        suffix=".tmp",
    )

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as handle:

            json.dump(
                state,
                handle,
                indent=2,
                ensure_ascii=False,
            )

            handle.flush()
            os.fsync(
                handle.fileno()
            )

        os.replace(
            tmp_path,
            TRACKER_FILE,
        )

    except Exception:

        try:
            if os.path.exists(
                tmp_path
            ):
                os.unlink(
                    tmp_path
                )
        except OSError:
            pass

        raise


def mark_section_read(
    article_id: str,
    section_type: str,
    char_start: int,
    extracted_items: Dict[str, int],
    reading_state: Dict,
) -> Dict:
    """
    Record a successfully processed article section.
    """

    if not article_id:
        return reading_state

    if not isinstance(
        reading_state,
        dict,
    ):
        reading_state = {}

    if article_id not in reading_state:

        reading_state[
            article_id
        ] = {
            "first_read_at": _utcnow(),
            "read_sections": [],
            "section_details": [],
            "total_extractions": {
                "concepts": 0,
                "equations": 0,
                "procedures": 0,
                "rules": 0,
            },
        }

    article = reading_state[
        article_id
    ]

    article.setdefault(
        "first_read_at",
        _utcnow(),
    )

    article.setdefault(
        "read_sections",
        [],
    )

    article.setdefault(
        "section_details",
        [],
    )

    article.setdefault(
        "total_extractions",
        {},
    )

    for key in (
        "concepts",
        "equations",
        "procedures",
        "rules",
    ):
        article[
            "total_extractions"
        ].setdefault(
            key,
            0,
        )

    try:
        char_start = int(
            char_start
        )
    except (
        TypeError,
        ValueError,
    ):
        char_start = 0

    section_key = (
        f"{section_type}_{char_start}"
    )

    if section_key in article[
        "read_sections"
    ]:
        return reading_state

    article[
        "read_sections"
    ].append(
        section_key
    )

    normalized_extractions = {}

    if isinstance(
        extracted_items,
        dict,
    ):
        for key, value in (
            extracted_items.items()
        ):
            try:
                numeric = int(
                    value
                )
            except (
                TypeError,
                ValueError,
            ):
                numeric = 0

            normalized_extractions[
                key
            ] = max(
                0,
                numeric,
            )

    article[
        "section_details"
    ].append(
        {
            "section_type": (
                str(section_type)
                if section_type
                else "unknown"
            ),
            "char_start": char_start,
            "read_at": _utcnow(),
            "extracted": normalized_extractions,
        }
    )

    for key, count in (
        normalized_extractions.items()
    ):
        if key in article[
            "total_extractions"
        ]:
            article[
                "total_extractions"
            ][key] += count

    return reading_state


def get_article_provenance(
    article_id: str,
    reading_state: Dict,
) -> Dict:
    """Return the provenance record for one article."""

    if (
        not isinstance(
            reading_state,
            dict,
        )
        or article_id
        not in reading_state
    ):
        return {
            "article_id": article_id,
            "status": "never_read",
            "sections": [],
        }

    article = reading_state[
        article_id
    ]

    return {
        "article_id": article_id,
        "first_read_at": article.get(
            "first_read_at",
            "unknown",
        ),
        "sections_read": len(
            article.get(
                "read_sections",
                [],
            )
        ),
        "total_extractions": article.get(
            "total_extractions",
            {},
        ),
        "section_details": article.get(
            "section_details",
            [],
        ),
    }


def get_unread_article_ids(
    reading_state: Dict,
    all_article_ids: List[str],
) -> List[str]:
    """
    Find articles for which reading is incomplete.

    The old implementation used a fixed heuristic of five sections.
    This function intentionally keeps that compatibility behavior,
    but handles malformed state safely.
    """

    unread = []

    if not isinstance(
        reading_state,
        dict,
    ):
        reading_state = {}

    for article_id in all_article_ids:

        if article_id not in reading_state:
            unread.append(
                article_id
            )
            continue

        article = reading_state[
            article_id
        ]

        details = article.get(
            "section_details",
            [],
        )

        if not isinstance(
            details,
            list,
        ):
            unread.append(
                article_id
            )
            continue

        if len(details) < 5:
            unread.append(
                article_id
            )

    return unread


def generate_provenance_report(
    reading_state: Dict,
) -> str:
    """
    Generate a human-readable provenance report.
    """

    lines = []

    if not isinstance(
        reading_state,
        dict,
    ):
        return ""

    for article_id, data in (
        reading_state.items()
    ):

        if not isinstance(
            data,
            dict,
        ):
            continue

        lines.append(
            f"\n\\subsection*{{{article_id}}}"
        )

        lines.append(
            "First read: "
            f"{data.get('first_read_at', 'unknown')}"
        )

        totals = data.get(
            "total_extractions",
            {},
        )

        if not isinstance(
            totals,
            dict,
        ):
            totals = {}

        lines.append(
            "Total extractions: "
            f"{totals.get('concepts', 0)} concepts, "
            f"{totals.get('equations', 0)} equations, "
            f"{totals.get('procedures', 0)} procedures, "
            f"{totals.get('rules', 0)} rules"
        )

        lines.append(
            "\n\\begin{itemize}"
        )

        details = data.get(
            "section_details",
            [],
        )

        if not isinstance(
            details,
            list,
        ):
            details = []

        for detail in details:

            if not isinstance(
                detail,
                dict,
            ):
                continue

            section_type = (
                str(
                    detail.get(
                        "section_type",
                        "unknown",
                    )
                )
                .replace(
                    "_",
                    " ",
                )
                .title()
            )

            extracted = detail.get(
                "extracted",
                {},
            )

            if not isinstance(
                extracted,
                dict,
            ):
                extracted = {}

            read_at = str(
                detail.get(
                    "read_at",
                    "unknown",
                )
            )[:10]

            items_str = ", ".join(
                f"{value} {key}"
                for key, value
                in extracted.items()
                if isinstance(
                    value,
                    int,
                )
                and value > 0
            )

            if items_str:

                lines.append(
                    "  \\item "
                    f"\\textbf{{{section_type}}} "
                    f"(read {read_at}): "
                    f"{items_str}"
                )

            else:

                lines.append(
                    "  \\item "
                    f"\\textbf{{{section_type}}} "
                    f"(read {read_at}): "
                    "no items extracted"
                )

        lines.append(
            "\\end{itemize}"
        )

    return "\n".join(
        lines
    )
