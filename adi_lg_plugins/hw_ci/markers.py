"""Harvest HW-CI markers from a caller repo via static AST parsing.

The discover step shouldn't import test modules: in pyadi-iio and
similar repos a top-level ``import adi`` dlopens libiio, which only
exists in a working form on the per-place runners (close to the DUT),
not on the coordinator-adjacent runner where ``discover`` runs.

So instead of ``pytest --collect-only`` (which imports modules), we
walk ``test_root`` with :mod:`ast` and read decorator literals
directly. The contract: ``@pytest.mark.iio_hardware([...])`` /
``@pytest.mark.iio_carrier([...])`` arguments must be **string
literals** (or a literal list/tuple of strings). Computed/dynamic
markers cannot be statically harvested — document this in the v2
guide rather than fall back to importing.

The companion ``adi_lg_plugins.pytest_plugin`` still registers the
markers at *test-run* time so ``--strict-markers`` is happy in the
consumer's hardware test runs.
"""

from __future__ import annotations

import ast
from pathlib import Path

from .intersect import MarkerSpec


def _is_pytest_mark(node: ast.expr, marker_name: str) -> bool:
    """True iff ``node`` is the attribute access ``pytest.mark.<marker_name>``."""
    if not isinstance(node, ast.Attribute) or node.attr != marker_name:
        return False
    parent = node.value
    if not isinstance(parent, ast.Attribute) or parent.attr != "mark":
        return False
    root = parent.value
    return isinstance(root, ast.Name) and root.id == "pytest"


def _literal_str_list(arg: ast.expr) -> list[str] | None:
    """Coerce an AST node into a list[str] if it's a literal form we accept.

    Accepts:
    * ``"ad9081"``                  → ``["ad9081"]``
    * ``["ad9081", "ad9081_tdd"]``  → ``["ad9081", "ad9081_tdd"]``
    * ``("ad9081",)``               → ``["ad9081"]``

    Returns None for any non-literal form (variable, f-string, etc.).
    """
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return [arg.value]
    if isinstance(arg, (ast.List, ast.Tuple)):
        out: list[str] = []
        for el in arg.elts:
            if isinstance(el, ast.Constant) and isinstance(el.value, str):
                out.append(el.value)
            else:
                return None
        return out
    return None


def _extract_marker_args(decorator: ast.expr, marker_name: str) -> list[str] | None:
    """If ``decorator`` is ``@pytest.mark.<marker_name>(arg)``, return arg as list[str].

    Returns None when the decorator doesn't match or when its argument
    isn't a recognised literal form.
    """
    if not isinstance(decorator, ast.Call):
        return None
    if not _is_pytest_mark(decorator.func, marker_name):
        return None
    if not decorator.args:
        return []
    return _literal_str_list(decorator.args[0])


def harvest_markers(
    test_root: str | Path,
    *,
    marker: str = "iio_hardware",
) -> dict[str, MarkerSpec]:
    """Walk ``test_root`` for ``test_*.py`` files and harvest hw-ci markers.

    Parameters
    ----------
    test_root :
        Directory to walk (typically a caller's ``test/hw/``).
    marker :
        Primary marker name. Tests without this marker are omitted from
        the result. Currently always ``iio_hardware`` in practice; the
        parameter exists so non-iio projects can plug in their own.

    Returns
    -------
    dict mapping ``"<relative-path>::<test-name>"`` to a
    :class:`MarkerSpec`. The companion ``iio_carrier`` marker is picked
    up on the same function and stored alongside.

    Files that fail to parse (syntax error, unreadable) are skipped
    with no exception — they're not test files we can harvest, and
    the consumer's own pytest run will surface the real error.
    """
    root = Path(test_root).resolve()
    carrier_marker = "iio_carrier"
    out: dict[str, MarkerSpec] = {}
    for py in sorted(root.rglob("test_*.py")):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            iio_hw: list[str] | None = None
            iio_carr: list[str] = []
            for dec in node.decorator_list:
                hw_args = _extract_marker_args(dec, marker)
                if hw_args is not None:
                    iio_hw = hw_args
                    continue
                carr_args = _extract_marker_args(dec, carrier_marker)
                if carr_args is not None:
                    iio_carr = carr_args
            if not iio_hw:
                continue
            rel = py.relative_to(root)
            test_id = f"{rel}::{node.name}"
            out[test_id] = MarkerSpec.of(iio_hw, iio_carr)
    return out
