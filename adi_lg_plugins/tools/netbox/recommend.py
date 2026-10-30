"""Which boot strategies a board's exported resources can run.

A place's ``boot-strategy`` tag makes render-env emit that strategy's config
(``adi_lg_plugins/hw_ci/templates/<strategy>.yaml``). Each driver the config
lists must find the resources it binds among the place's, or the place can't
run the strategy. The needs are read from those configs and the drivers'
labgrid ``bindings``, so there is no table to keep in step with either.
"""

from __future__ import annotations

import string
from collections import defaultdict
from collections.abc import Collection
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
