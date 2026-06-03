"""Board catalog: load board_catalog.yaml and resolve part -> image/version/metadata.

Pure logic, no FastAPI imports, so it is unit-testable in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


class CatalogError(Exception):
    """Base class for catalog resolution failures."""


class UnknownPart(CatalogError):
    """The requested part is not in the catalog."""


class UnresolvableVersion(CatalogError):
    """No bootfile pin given and no channel version could be resolved."""


@dataclass(frozen=True)
class CarrierEntry:
    matlab_board: str | None = None


@dataclass(frozen=True)
class BoardEntry:
    part: str
    image_channel: str | None
    carriers: dict[str, CarrierEntry] = field(default_factory=dict)


@dataclass(frozen=True)
class Catalog:
    channels: dict[str, str] = field(default_factory=dict)
    boards: dict[str, BoardEntry] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedBoard:
    part: str
    version: str | None
    matlab_boards: dict[str, str]


def load_catalog(path: str | Path) -> Catalog:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    channels = {str(k): str(v) for k, v in (raw.get("channels") or {}).items()}
    boards: dict[str, BoardEntry] = {}
    for part, entry in (raw.get("boards") or {}).items():
        entry = entry or {}
        carriers = {
            str(cname): CarrierEntry(matlab_board=(cval or {}).get("matlab_board"))
            for cname, cval in (entry.get("carriers") or {}).items()
        }
        boards[str(part)] = BoardEntry(
            part=str(part),
            image_channel=entry.get("image_channel"),
            carriers=carriers,
        )
    return Catalog(channels=channels, boards=boards)


def resolve_board(
    catalog: Catalog,
    *,
    part: str,
    carrier: str | None = None,
    bootfile: str | None = None,
) -> ResolvedBoard:
    """Resolve a request into a concrete image version + per-carrier MATLAB names.

    `carrier` is accepted for symmetry/validation but does not change version
    resolution in Phase 1. A pinned `bootfile` is taken as-is; otherwise the
    board's channel "latest" is used.
    """
    board = catalog.boards.get(part)
    if board is None:
        raise UnknownPart(f"part '{part}' is not in the board catalog")

    if bootfile:
        version: str | None = bootfile
    elif board.image_channel and board.image_channel in catalog.channels:
        version = catalog.channels[board.image_channel]
    else:
        raise UnresolvableVersion(
            f"part '{part}' has no pinned bootfile and no resolvable image channel"
        )

    matlab_boards = {cname: c.matlab_board for cname, c in board.carriers.items() if c.matlab_board}
    return ResolvedBoard(part=part, version=version, matlab_boards=matlab_boards)
