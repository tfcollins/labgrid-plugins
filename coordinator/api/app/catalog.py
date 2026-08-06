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


class FlashConfig(BaseModel):
    """no-os "flash" mode support for a board: which strategy loads the
    firmware and which ``projects/<noos_project>`` builds it. Present only on
    boards that can run no-os bare-metal firmware (vs. the Kuiper SD boot)."""

    strategy: str
    noos_project: str
    # Per-board JTAG target override; when None the env_gen / strategy default
    # ("*Cortex-A9 MPCore #0") applies.
    a9_target_name: str | None = None
    # Explicit Kuiper boot-partition folder holding bootgen_sysfiles.tgz; when
    # None, build-noos searches the FAT partition for *<carrier>*<board>*.
    kuiper_xsa_dir: str | None = None


class BoardEntry(BaseModel):
    # Default boot image (a KuiperRelease version). None for boards that boot
    # by loading the FPGA fabric via JTAG (BootFabric, e.g. daq3) and so have
    # no downloadable image; a per-request --bootfile can still pin one.
    image: str | None = None
    # Alternate request names that resolve to this (canonical) board. Lets a
    # chip name like "ad9371" map to its eval-board key "adrv9371" (the place
    # tag), keeping the 1:1 part==daughter-board contract for matching.
    aliases: list[str] = []
    # no-os firmware "flash" mode capability (None = Kuiper-only board).
    flash: FlashConfig | None = None
    carriers: dict[str, BoardCarrier] = {}


class BoardCatalog(BaseModel):
    boards: dict[str, BoardEntry] = {}

    def lookup(self, part: str) -> tuple[str, BoardEntry] | None:
        """Resolve a requested part to ``(canonical_key, entry)``.

        Tries a direct board key first, then any entry's ``aliases``. Returns
        None if nothing matches. The canonical key is what callers must use as
        the ``daughter-board`` reservation filter (it equals the place tag).
        """
        entry = self.boards.get(part)
        if entry is not None:
            return part, entry
        for key, candidate in self.boards.items():
            if part in candidate.aliases:
                return key, candidate
        return None


def load_catalog(path: str) -> BoardCatalog:
    """Load and validate the catalog. A missing file yields an empty
    catalog (and a warning) rather than crashing startup."""
    p = Path(path)
    if not p.exists():
        logger.warning("board catalog not found at %s; serving empty catalog", path)
        return BoardCatalog()
    data = yaml.safe_load(p.read_text()) or {}
    return BoardCatalog.model_validate(data)


def resolve_image(entry: BoardEntry, bootfile: str | None) -> str | None:
    """A pinned bootfile wins; otherwise the board's default image (which may
    be None for fabric-load boards that have no downloadable image)."""
    return bootfile or entry.image


def save_catalog(catalog: BoardCatalog, path: str) -> None:
    """Save the catalog to the specified YAML file path."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = catalog.model_dump(exclude_none=True)
    p.write_text(yaml.safe_dump(data, sort_keys=False))
