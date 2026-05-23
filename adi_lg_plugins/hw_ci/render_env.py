"""Render a per-job labgrid env yaml from a place's tags.

The reusable workflow invokes this once per matrix entry, before the
shard runs. The env yaml contains:

* a ``RemotePlace`` binding to the place name, and
* the driver + strategy stack the place's ``boot-strategy`` tag implies.

Templates live as ``.yaml`` files in :mod:`adi_lg_plugins.hw_ci.templates`
named ``<BootStrategyClassName>.yaml`` — one per strategy registered
in :mod:`adi_lg_plugins.strategies`. Each template uses
:class:`string.Template` ``${var}`` substitution (no jinja dep needed):

* ``${place_name}``      — the place to bind ``RemotePlace`` to
* ``${carrier}``         — informational, may appear in comments
* ``${daughter_board}``  — informational
* ``${hdl_config}``      — optional narrowing; empty string if absent

Adding a new strategy is a no-code op: drop a yaml with the right
filename. :func:`render_env` raises a clear error if the strategy
tag is set but no template exists.
"""

from __future__ import annotations

import string
from collections.abc import Mapping
from importlib import resources
from pathlib import Path

from .schema import Place

_TEMPLATES_PKG = "adi_lg_plugins.hw_ci.templates"


class RenderError(RuntimeError):
    """No template available for a place's boot-strategy."""


def list_strategy_templates() -> list[str]:
    """Names (without ``.yaml`` extension) of known templates."""
    try:
        entries = resources.files(_TEMPLATES_PKG).iterdir()
    except (ModuleNotFoundError, FileNotFoundError):
        return []
    names = []
    for entry in entries:
        if entry.is_file() and entry.name.endswith(".yaml"):
            names.append(entry.name[: -len(".yaml")])
    return sorted(names)


def _load_template(strategy: str) -> str:
    try:
        return (
            resources.files(_TEMPLATES_PKG).joinpath(f"{strategy}.yaml").read_text(encoding="utf-8")
        )
    except (ModuleNotFoundError, FileNotFoundError) as e:
        raise RenderError(
            f"no env-yaml template for boot-strategy {strategy!r}; "
            f"available: {list_strategy_templates() or '(none)'}"
        ) from e


def render_env(
    place: Place,
    *,
    extra_subs: Mapping[str, str] | None = None,
) -> str:
    """Return the env-yaml string for this place.

    ``extra_subs`` lets the caller inject project-specific values; keys
    collide with the built-in substitutions silently in favour of the
    caller's values.
    """
    template_text = _load_template(place.boot_strategy)
    # `power-driver` is an optional place tag carrying the labgrid driver
    # class name to use for power control (e.g. `VesyncPowerDriver`,
    # `HomeAssistantDriver`). Different lab setups use different power
    # outlets per board, and labgrid binds drivers to resources by class
    # name — so the env yaml must list the driver class that matches the
    # outlet resource the place actually exposes. Defaults to
    # `VesyncPowerDriver` for back-compat with the first generation of
    # ADI lab places.
    power_driver = place.extra_tags.get("power-driver", "VesyncPowerDriver")
    # Per-place local TFTP root used by templates that need a writable
    # root for KuiperDLDriver (BootFPGASoCTFTP). Per-place to avoid two
    # parallel runs colliding; overridable via extra_subs / a tag.
    tftp_root = place.extra_tags.get("tftp-root", f"/tmp/labgrid-tftp-{place.name}")
    subs: dict[str, str] = {
        "place_name": place.name,
        "carrier": place.carrier,
        "daughter_board": place.daughter_board,
        "hdl_config": place.hdl_config or "",
        "board_location": place.board_location or "",
        "power_driver": power_driver,
        "tftp_root": tftp_root,
    }
    if extra_subs:
        subs.update({str(k): str(v) for k, v in extra_subs.items()})
    return string.Template(template_text).safe_substitute(subs)


def render_env_to(place: Place, out_path: Path, **kw) -> Path:
    """Render and write to disk; return the path."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_env(place, **kw), encoding="utf-8")
    return out_path
