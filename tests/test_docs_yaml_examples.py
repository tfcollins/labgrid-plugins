"""Every YAML example in the docs must load with the loader labgrid applies to it.

Exporter ``resources.yaml`` examples go through ``labgrid-exporter``'s
``ResourceConfig`` (Jinja with ``#`` line statements, then labgrid's YAML
loader); client ``target.yaml`` examples go through labgrid's YAML loader,
which only adds the ``!template`` tag. Unknown tags such as ``!env`` or a
``#`` comment line in an exporter file stop labgrid before any driver runs.

Client configs are also held to the top-level keys labgrid's ``Config`` reads
(there is no ``includes:``), with no duplicate keys - labgrid only warns and
keeps the last one.
"""

from __future__ import annotations

import re
import textwrap
import warnings
from pathlib import Path

import pytest
from labgrid.remote.config import ResourceConfig
from labgrid.util.yaml import load

DOCS = Path(__file__).resolve().parents[1] / "docs" / "source"
_BLOCK = re.compile(r"^(?P<indent>[ \t]*)\.\. code-block:: yaml(\+jinja)?[ \t]*$")
# Top-level keys labgrid.config.Config reads from a client environment file.
_CLIENT_KEYS = {"targets", "imports", "options", "paths", "images", "tools", "features"}


def _yaml_blocks():
    for path in sorted(DOCS.rglob("*.rst")):
        lines = path.read_text(encoding="utf-8").splitlines()
        i = 0
        while i < len(lines):
            match = _BLOCK.match(lines[i])
            if not match:
                i += 1
                continue
            indent = len(match.group("indent"))
            j = i + 1
            while j < len(lines) and (
                not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) > indent
            ):
                j += 1
            body = [line for line in lines[i + 1 : j] if not line.strip().startswith(":")]
            text = textwrap.dedent("\n".join(body)).strip("\n")
            if text:
                yield pytest.param(text, id=f"{path.relative_to(DOCS)}:{i + 1}")
            i = j


def _is_exporter_config(text: str) -> bool:
    return "cls:" in text and not re.search(r"^\s*targets:", text, re.M)


@pytest.mark.parametrize("text", list(_yaml_blocks()))
def test_docs_yaml_example_loads_in_labgrid(text, tmp_path):
    if _is_exporter_config(text):
        config = tmp_path / "resources.yaml"
        config.write_text(text + "\n")
        ResourceConfig(str(config), {"env": {}, "isolated": False, "hostname": "h", "name": "n"})
    elif re.search(r"^\s*targets:", text, re.M):
        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)  # duplicate keys
            data = load(text)
        unknown = set(data) - _CLIENT_KEYS if "targets" in data else set()
        assert not unknown, f"labgrid client configs have no top-level {sorted(unknown)} key"
    elif re.search(r"^resources:", text, re.M):
        pytest.fail(
            "top-level `resources:` without `targets:` is neither an exporter config nor "
            "a client config - labgrid cannot include it from another file"
        )
    else:
        pytest.skip("not a labgrid exporter or client config")
