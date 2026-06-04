from __future__ import annotations

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
    # Extensibility: future per-carrier metadata must not break parsing,
    # and `extra="allow"` must RETAIN it (default extra="ignore" would drop it).
    extended = """\
boards:
  adrv9002:
    image: kuiper-2023_R2
    carriers:
      zcu102:
        matlab_board: some-future-name
"""
    cat = load_catalog(_write(tmp_path, extended))
    carrier = cat.boards["adrv9002"].carriers["zcu102"]
    assert carrier.model_extra == {"matlab_board": "some-future-name"}


def test_resolve_image_defaults_to_catalog(tmp_path):
    cat = load_catalog(_write(tmp_path, FIXTURE))
    entry = cat.boards["adrv9002"]
    assert resolve_image(entry, None) == "kuiper-2023_R2"


def test_resolve_image_honors_pin(tmp_path):
    cat = load_catalog(_write(tmp_path, FIXTURE))
    entry = cat.boards["adrv9002"]
    assert resolve_image(entry, "2023_R2_P1") == "2023_R2_P1"


def test_load_catalog_empty_file_returns_empty(tmp_path):
    cat = load_catalog(_write(tmp_path, ""))
    assert cat.boards == {}


# The real catalog file shipped into the API image (repo-root copy). A place
# tagged for a part that has no entry here surfaces to users as "unknown part",
# so this file must keep pace with the lab's advertised places.
SHIPPED_CATALOG = Path(__file__).resolve().parent.parent / "board_catalog.yaml"


def test_shipped_catalog_declares_every_lab_board():
    """Each coordinator place's daughter-board must have a catalog entry.

    Lab places (2026-06): mini2=adrv9002/zcu102 (BootFPGASoC),
    nemo=adrv9009/zc706 and bq=adrv9371/zc706 (BootZynq7000JTAGRecovery).
    adrv9371 is the AD9371 eval board (pyadi ``adi.ad9371``; the HW smoke
    test marks ``iio_hardware('adrv9371')``).
    """
    cat = load_catalog(str(SHIPPED_CATALOG))
    assert "adrv9002" in cat.boards and "zcu102" in cat.boards["adrv9002"].carriers
    assert "adrv9009" in cat.boards and "zc706" in cat.boards["adrv9009"].carriers
    assert "adrv9371" in cat.boards and "zc706" in cat.boards["adrv9371"].carriers


def test_shipped_catalog_images_are_pinned_not_placeholders():
    """Every shipped entry pins a real KuiperRelease version, never a
    ``kuiper-...`` placeholder (a placeholder would break a real boot)."""
    cat = load_catalog(str(SHIPPED_CATALOG))
    for name, entry in cat.boards.items():
        assert not entry.image.startswith("kuiper-"), (
            f"{name!r} image is a placeholder: {entry.image!r}"
        )
