from pathlib import Path

from app.catalog import BoardCatalog, load_catalog, resolve_image

FIXTURE = """\
boards:
  adrv9002:
    image: kuiper-2023_R2
    carriers:
      zcu102: {}
"""


def _write(tmp_path: Path, text: str) -> str:
    p = tmp_path / "board_catalog.yaml"
    p.write_text(text)
    return str(p)


def test_load_catalog_parses_board(tmp_path):
    cat = load_catalog(_write(tmp_path, FIXTURE))
    assert isinstance(cat, BoardCatalog)
    assert "adrv9002" in cat.boards
    entry = cat.boards["adrv9002"]
    assert entry.image == "kuiper-2023_R2"
    assert "zcu102" in entry.carriers


def test_load_catalog_missing_file_returns_empty(tmp_path):
    cat = load_catalog(str(tmp_path / "does_not_exist.yaml"))
    assert cat.boards == {}


def test_load_catalog_ignores_unknown_carrier_fields(tmp_path):
    # Extensibility: future per-carrier metadata must not break parsing.
    extended = """\
boards:
  adrv9002:
    image: kuiper-2023_R2
    carriers:
      zcu102:
        matlab_board: some-future-name
"""
    cat = load_catalog(_write(tmp_path, extended))
    assert "zcu102" in cat.boards["adrv9002"].carriers


def test_resolve_image_defaults_to_catalog(tmp_path):
    cat = load_catalog(_write(tmp_path, FIXTURE))
    entry = cat.boards["adrv9002"]
    assert resolve_image(entry, None) == "kuiper-2023_R2"


def test_resolve_image_honors_pin(tmp_path):
    cat = load_catalog(_write(tmp_path, FIXTURE))
    entry = cat.boards["adrv9002"]
    assert resolve_image(entry, "2023_R2_P1") == "2023_R2_P1"
