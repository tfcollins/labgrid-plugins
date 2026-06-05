"""Map a coordinator place's tags to a MATLAB board reference name.

labgrid place tags describe hardware as ``(carrier, daughter-board,
hdl-config)`` — e.g. ``zcu102`` + ``adrv9002``. MATLAB toolboxes such as
TransceiverToolbox instead key their HW test entry points on long HDL
reference names (e.g. ``zynqmp-zcu102-rev10-adrv9002-vcmos``, the values
in ``runHWTests.m``'s ``switch``). This module bridges that gap with a
consumer-supplied YAML board map.

Board-map file format::

    boards:
      - {carrier: zcu102, daughter-board: adrv9002, matlab_board: zynqmp-zcu102-rev10-adrv9002-vcmos}
      - {daughter-board: ad9361, matlab_board: zynq-zed-adv7511-ad9361-fmcomms2-3}

Each entry must carry ``daughter-board`` and ``matlab_board``. ``carrier``
and ``hdl-config`` are optional narrowing keys: an entry with them set
only matches a place whose tags agree, and the *most specific* matching
entry wins. The loader/schema is generic; the file content is
toolbox-specific.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from adi_lg_plugins.hw_ci.schema import Place


class BoardMapError(ValueError):
    """The board-map file is missing, malformed, or has invalid entries."""


@dataclass(frozen=True)
class BoardMapEntry:
    """One ``(tags) -> matlab board name`` row of the board map."""

    matlab_board: str
    daughter_board: str
    carrier: str | None = None
    hdl_config: str | None = None

    @property
    def specificity(self) -> int:
        """How many optional narrowing keys this entry constrains."""
        return int(self.carrier is not None) + int(self.hdl_config is not None)

    def matches(self, place: Place) -> bool:
        if self.daughter_board != place.daughter_board:
            return False
        if self.carrier is not None and self.carrier != place.carrier:
            return False
        if self.hdl_config is not None and self.hdl_config != place.hdl_config:
            return False
        return True


@dataclass(frozen=True)
class BoardMap:
    """An ordered set of :class:`BoardMapEntry` rows."""

    entries: tuple[BoardMapEntry, ...]

    def lookup(self, place: Place) -> str | None:
        """Return the MATLAB board name for ``place``, or ``None``.

        Among all matching entries, the most specific (most narrowing
        keys) wins. Ties resolve to the first entry in file order.
        """
        matches = [e for e in self.entries if e.matches(place)]
        if not matches:
            return None
        best = max(matches, key=lambda e: e.specificity)
        return best.matlab_board


def load_board_map(path: str | Path) -> BoardMap:
    """Parse a board-map YAML file into a :class:`BoardMap`.

    Raises :class:`BoardMapError` on a missing file, non-mapping top
    level, missing ``boards:`` list, or an entry without the required
    ``daughter-board`` / ``matlab_board`` keys.
    """
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise BoardMapError(f"board-map file not found: {path}") from e
    except yaml.YAMLError as e:
        raise BoardMapError(f"board-map file {path} is not valid YAML: {e}") from e

    if not isinstance(raw, dict) or "boards" not in raw:
        raise BoardMapError(f"board-map file {path} must have a top-level 'boards:' list")
    boards = raw["boards"]
    if not isinstance(boards, list):
        raise BoardMapError(f"board-map file {path}: 'boards' must be a list")

    entries: list[BoardMapEntry] = []
    for i, row in enumerate(boards):
        if not isinstance(row, dict):
            raise BoardMapError(f"board-map file {path}: entry #{i} is not a mapping")
        daughter = row.get("daughter-board")
        matlab_board = row.get("matlab_board")
        if not daughter or not matlab_board:
            raise BoardMapError(
                f"board-map file {path}: entry #{i} must set both "
                f"'daughter-board' and 'matlab_board'; got {sorted(row)}"
            )
        entries.append(
            BoardMapEntry(
                matlab_board=str(matlab_board),
                daughter_board=str(daughter),
                carrier=str(row["carrier"]) if row.get("carrier") else None,
                hdl_config=str(row["hdl-config"]) if row.get("hdl-config") else None,
            )
        )
    return BoardMap(entries=tuple(entries))
