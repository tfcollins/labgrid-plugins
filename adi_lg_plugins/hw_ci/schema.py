"""Place tag schema for HW-CI v2.

Defines the contract every place on the coordinator must satisfy to be
eligible for the matrix:

* ``carrier``        — the FPGA carrier (zcu102, zc706, vcu118, rpi5, …)
* ``daughter-board`` — the mezzanine / daughter chip (ad9081, adrv9371, …)
* ``boot-strategy``  — the strategy class name (must match one of the
                       classes registered in ``adi_lg_plugins.strategies``)
* ``hdl-config``     — optional; further-narrowing string

The strategy registry is introspected at import time so any new
``Boot*`` strategy added under ``adi_lg_plugins.strategies`` is
automatically a valid tag value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

# Required-and-validated tag keys. Order is the documented schema order.
REQUIRED_TAGS = ("carrier", "daughter-board", "boot-strategy")
OPTIONAL_TAGS = ("hdl-config", "board-location")


class PlaceValidationError(ValueError):
    """A place's tags don't satisfy the HW-CI v2 schema."""


@dataclass(frozen=True)
class Place:
    """A coordinator place narrowed to its HW-CI surface.

    Constructed via :func:`validate_place` from the raw dict returned
    by the coordinator's ``/api/places`` endpoint.
    """

    name: str
    carrier: str
    daughter_board: str
    boot_strategy: str
    hdl_config: str | None = None
    board_location: str | None = None
    acquired: str | None = None
    extra_tags: dict[str, str] = field(default_factory=dict)

    @property
    def is_acquired(self) -> bool:
        return bool(self.acquired)


def _strategy_registry() -> set[str]:
    """Names of strategy classes the coordinator may legally reference.

    Pulled by introspection of :mod:`adi_lg_plugins.strategies` so adding
    a new ``Boot*`` class is automatically a valid ``boot-strategy``
    tag value with no schema edit.
    """
    import importlib
    import inspect
    import pkgutil

    try:
        from adi_lg_plugins import strategies as strategies_pkg
    except ImportError:  # pragma: no cover — only if package isn't installed
        return set()

    names: set[str] = set()
    for mod_info in pkgutil.iter_modules(strategies_pkg.__path__):
        try:
            mod = importlib.import_module(
                f"{strategies_pkg.__name__}.{mod_info.name}"
            )
        except Exception:  # noqa: BLE001 — best-effort introspection
            continue
        for cls_name, cls_obj in inspect.getmembers(mod, inspect.isclass):
            # Strategies defined here, not imported into the module.
            if cls_obj.__module__ != mod.__name__:
                continue
            if not cls_name.startswith("Boot"):
                continue
            names.add(cls_name)
    return names


# Resolved once at import. Tests can monkeypatch ``KNOWN_STRATEGIES`` to
# inject fake strategy names without touching the strategies package.
KNOWN_STRATEGIES: frozenset[str] = frozenset(_strategy_registry())


def validate_place(
    raw: dict,
    *,
    known_strategies: Iterable[str] | None = None,
) -> Place:
    """Turn a raw ``/api/places`` dict into a validated :class:`Place`.

    Raises :class:`PlaceValidationError` on any of:

    * missing ``name``
    * any required tag absent
    * ``boot-strategy`` value not in the strategy registry

    ``known_strategies`` is an injection seam for tests; production
    callers should leave it ``None`` to use the live registry.
    """
    name = raw.get("name")
    if not name:
        raise PlaceValidationError("place has no name")

    tags_raw = raw.get("tags") or {}
    # The coordinator REST API returns tags as a dict; the labgrid-client
    # `show` parser returns a comma-joined string. Accept either.
    if isinstance(tags_raw, str):
        tags: dict[str, str] = {}
        for kv in tags_raw.split(","):
            kv = kv.strip()
            if "=" not in kv:
                continue
            k, v = kv.split("=", 1)
            tags[k.strip()] = v.strip()
    elif isinstance(tags_raw, dict):
        tags = {str(k): str(v) for k, v in tags_raw.items()}
    else:
        raise PlaceValidationError(
            f"place {name!r}: tags must be dict or string, got {type(tags_raw).__name__}"
        )

    missing = [t for t in REQUIRED_TAGS if not tags.get(t)]
    if missing:
        raise PlaceValidationError(
            f"place {name!r}: missing required tag(s) "
            f"{', '.join(missing)}; have {sorted(tags)}"
        )

    boot_strategy = tags["boot-strategy"]
    registry = (
        frozenset(known_strategies) if known_strategies is not None
        else KNOWN_STRATEGIES
    )
    if registry and boot_strategy not in registry:
        raise PlaceValidationError(
            f"place {name!r}: boot-strategy {boot_strategy!r} is not a "
            f"known strategy; valid values are {sorted(registry)}"
        )

    consumed = set(REQUIRED_TAGS) | set(OPTIONAL_TAGS)
    extra = {k: v for k, v in tags.items() if k not in consumed}

    return Place(
        name=name,
        carrier=tags["carrier"],
        daughter_board=tags["daughter-board"],
        boot_strategy=boot_strategy,
        hdl_config=tags.get("hdl-config"),
        board_location=tags.get("board-location"),
        acquired=raw.get("acquired") or None,
        extra_tags=extra,
    )
