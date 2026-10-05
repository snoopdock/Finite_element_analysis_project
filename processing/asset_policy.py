"""Publication-safe policy for figure asset references.

Semantic Figure.asset values are identifiers for publication assets, not raw
LaTeX.  The LaTeX boundary accepts only portable repository-relative paths
using a small filename alphabet and known graphics extensions.  It never
normalizes traversal or interprets URLs/commands on the user's behalf.
"""

from __future__ import annotations

from pathlib import PurePosixPath
import re


class AssetPathError(ValueError):
    """Raised when a figure asset path is unsafe or non-portable."""


_SAFE_ASSET_RE = re.compile(r"[A-Za-z0-9._/-]+")
_ALLOWED_SUFFIXES = frozenset({".pdf", ".png", ".jpg", ".jpeg"})


def validate_figure_asset_path(asset: str) -> str:
    """Return ``asset`` only when it is a safe portable relative graphics path."""
    if not isinstance(asset, str) or not asset.strip():
        raise AssetPathError("figure asset must be a non-empty string")
    if asset != asset.strip():
        raise AssetPathError("figure asset must not contain leading/trailing whitespace")
    if "\\" in asset:
        raise AssetPathError("figure asset must use POSIX '/' separators")
    if "://" in asset:
        raise AssetPathError("figure asset URLs are not accepted at the LaTeX boundary")
    if not _SAFE_ASSET_RE.fullmatch(asset):
        raise AssetPathError(
            "figure asset contains unsupported path characters; use letters, digits, '.', '_', '-', and '/'"
        )

    path = PurePosixPath(asset)
    if path.is_absolute() or asset.startswith("/"):
        raise AssetPathError("figure asset must be repository-relative")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise AssetPathError("figure asset must not contain empty, '.' or '..' path segments")
    if path.suffix.lower() not in _ALLOWED_SUFFIXES:
        raise AssetPathError(
            "figure asset must use one of: .pdf, .png, .jpg, .jpeg"
        )
    return asset
