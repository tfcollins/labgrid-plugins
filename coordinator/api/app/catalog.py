"""Board catalog: part -> default image + valid carriers.

The catalog enriches place tags; it never duplicates them. Places remain
the source of truth for what hardware exists and is free. The catalog adds
how to provision/identify a board (default image now; per-surface metadata
like a MATLAB board name or flash method later).
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class BoardCarrier(BaseModel):
    """Per-carrier catalog entry. Empty today; extensible.

    `extra="allow"` lets future per-surface fields (e.g. a MATLAB board
    name, a flash method) be added to the data file without breaking
    older parsers.
    """

    model_config = {"extra": "allow"}


class BoardEntry(BaseModel):
    image: str
    carriers: dict[str, BoardCarrier] = {}


class BoardCatalog(BaseModel):
    boards: dict[str, BoardEntry] = {}


def load_catalog(path: str) -> BoardCatalog:
    """Load and validate the catalog. A missing file yields an empty
    catalog (and a warning) rather than crashing startup."""
    p = Path(path)
    if not p.exists():
        logger.warning("board catalog not found at %s; serving empty catalog", path)
        return BoardCatalog()
    data = yaml.safe_load(p.read_text()) or {}
    return BoardCatalog.model_validate(data)


def resolve_image(entry: BoardEntry, bootfile: str | None) -> str:
    """A pinned bootfile wins; otherwise the board's default image."""
    return bootfile or entry.image
