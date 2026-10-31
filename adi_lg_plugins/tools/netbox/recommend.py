"""Which exporter templates suit a board's hardware, and which boot strategies they can run.

A template exports resources for the hardware a board is wired to; beyond its
serial console and network, which every board has, some use a JTAG cable or a
USB SD mux, which only some boards have.

A place's ``boot-strategy`` tag makes render-env emit that strategy's config
(``adi_lg_plugins/hw_ci/templates/<strategy>.yaml``). Each driver the config
lists must find the resources it binds among the place's, or the place can't
run the strategy. The needs are read from those configs and the drivers'
labgrid ``bindings``, so there is no table to keep in step with either.
"""

from __future__ import annotations

import string
from collections import defaultdict
from collections.abc import Collection, Mapping
from functools import cache

import yaml
from labgrid.factory import target_factory

from adi_lg_plugins.hw_ci import render_env


def _needs(target: dict) -> frozenset[frozenset[str]]:
    """The resources a render-env target's drivers bind and it doesn't define itself.

    Each need is the set of resource classes any one of which will do. Optional
    bindings, and bindings to drivers or protocols (the target's other drivers
    provide those), are not needs.
    """
    resources = target.get("resources") or {}
    local = set(resources) | {
        r["cls"] for r in resources.values() if isinstance(r, dict) and "cls" in r
    }
    # Drivers bind base classes too (SerialDriver: a SerialPort), which aren't registered.
    resource_classes = {c.__name__ for r in target_factory.resources.values() for c in r.__mro__}
    needs = set()
    for driver in target.get("drivers") or {}:
        cls = target_factory.drivers.get(driver)
        for value in getattr(cls, "bindings", {}).values():
            alternatives = value if isinstance(value, set) else {value}
            if None in alternatives:
                continue
            names = {a if isinstance(a, str) else a.__name__ for a in alternatives}
            classes = frozenset(names & resource_classes)
            if classes and not classes & local:
                needs.add(classes)
    return frozenset(needs)


@cache
def strategy_needs(strategy: str) -> frozenset[frozenset[str]]:
    """The exported resources ``strategy``'s render-env config binds."""
    # Any value fills the placeholders; the power driver names a class that
    # isn't registered, so it is passed over - every board has its power.
    subs = defaultdict(lambda: "x", power_driver="power", power_output_driver="")
    text = string.Template(render_env._load_template(strategy)).safe_substitute(subs)
    return _needs(yaml.safe_load(text)["targets"]["main"])


def _label(classes: frozenset[str]) -> str:
    # NetworkSerialPort is what a client sees of an exported SerialPort.
    return " or ".join(
        sorted(c for c in classes if not (c.startswith("Network") and c[7:] in classes))
    )


def missing(strategy: str, exported: Collection[str]) -> list[str]:
    """What ``strategy`` needs that resources of the classes ``exported`` don't give it.

    An exported class gives what its base classes are needed for (a
    RawSerialPort is a SerialPort).
    """
    have = set()
    for name in exported:
        cls = target_factory.resources.get(name)
        have |= {c.__name__ for c in cls.__mro__} if cls else {name}
    gaps = [n for n in strategy_needs(strategy) if not n & have]
    # A need any of whose classes another one asks for is met along with it.
    return sorted({_label(g) for g in gaps if not any(o < g for o in gaps)})


# The exported resources that use board hardware not every board has.
_HARDWARE = {
    "XilinxDeviceJTAG": "jtag",
    "XilinxVivadoTool": "jtag",  # programs the board over the JTAG cable
    "USBSDMuxDevice": "sdmux",
    "MassStorageDevice": "sdmux",  # the SD mux's card reader
}
HARDWARE_LABELS = {"jtag": "JTAG", "sdmux": "SD mux"}


def hardware_used(exported: Collection[str]) -> frozenset[str]:
    """The board hardware (``jtag``, ``sdmux``) resources of the classes ``exported`` use."""
    return frozenset(_HARDWARE[c] for c in exported if c in _HARDWARE)


def lacking(exported: Collection[str], hardware: Collection[str]) -> list[str]:
    """What a template exporting ``exported`` uses that a board with ``hardware`` lacks."""
    return sorted(HARDWARE_LABELS[h] for h in hardware_used(exported) - set(hardware))


def rank_templates(
    templates: Mapping[str, Collection[str]], hardware: Collection[str]
) -> list[tuple[str, str]]:
    """The templates a board with ``hardware`` can use, best first, each with its fit.

    ``templates`` maps each template to the classes it exports. Those using the
    most of the board's hardware are "recommended", the others "fits"; a tie
    stays a tie, in name order.
    """
    fit = {t: len(hardware_used(e)) for t, e in templates.items() if not lacking(e, hardware)}
    best = max(fit.values(), default=0)
    return [
        (t, "recommended" if used == best else "fits")
        for t, used in sorted(fit.items(), key=lambda item: (-item[1], item[0]))
    ]
