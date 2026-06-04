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


def test_lookup_direct_key(tmp_path):
    cat = load_catalog(_write(tmp_path, FIXTURE))
    key, entry = cat.lookup("adrv9002")
    assert key == "adrv9002"
    assert entry.image == "kuiper-2023_R2"


def test_lookup_resolves_alias_to_canonical(tmp_path):
    aliased = """\
boards:
  adrv9371:
    aliases: [ad9371]
    image: 2023_R2_P1
    carriers:
      zc706: {}
"""
    cat = load_catalog(_write(tmp_path, aliased))
    key, entry = cat.lookup("ad9371")
    assert key == "adrv9371"
    assert "zc706" in entry.carriers


def test_lookup_unknown_returns_none(tmp_path):
    cat = load_catalog(_write(tmp_path, FIXTURE))
    assert cat.lookup("nosuchpart") is None


def test_flash_block_parses(tmp_path):
    text = """\
boards:
  adrv9371:
    image: 2023_R2_P1
    flash:
      strategy: BootNoOSJTAG
      noos_project: ad9371
    carriers:
      zc706: {}
"""
    cat = load_catalog(_write(tmp_path, text))
    fl = cat.boards["adrv9371"].flash
    assert fl is not None
    assert fl.strategy == "BootNoOSJTAG"
    assert fl.noos_project == "ad9371"


def test_board_without_flash_block_has_none(tmp_path):
    cat = load_catalog(_write(tmp_path, FIXTURE))
    assert cat.boards["adrv9002"].flash is None


def test_image_is_optional_for_fabric_boards(tmp_path):
    fabric = """\
boards:
  daq3:
    carriers:
      vcu118: {}
"""
    cat = load_catalog(_write(tmp_path, fabric))
    entry = cat.boards["daq3"]
    assert entry.image is None
    assert resolve_image(entry, None) is None
    assert resolve_image(entry, "some-bitstream") == "some-bitstream"


# The real catalog file shipped into the API image (repo-root copy). A place
# tagged for a part that has no entry here surfaces to users as "unknown part",
# so this file must keep pace with the lab's advertised places.
SHIPPED_CATALOG = Path(__file__).resolve().parent.parent / "board_catalog.yaml"


def test_shipped_catalog_declares_every_lab_board():
    """Each coordinator place's daughter-board must have a catalog entry.

    Lab places (2026-06): mini2=adrv9002/zcu102 (BootFPGASoC),
    nemo=adrv9009/zc706 and bq=adrv9371/zc706 (BootZynq7000JTAGRecovery),
    nuc=daq3/vcu118 (BootFabric). adrv9371 is the AD9371 eval board (pyadi
    ``adi.ad9371``; the HW smoke test marks ``iio_hardware('adrv9371')``).
    """
    cat = load_catalog(str(SHIPPED_CATALOG))
    assert "adrv9002" in cat.boards and "zcu102" in cat.boards["adrv9002"].carriers
    assert "adrv9009" in cat.boards and "zc706" in cat.boards["adrv9009"].carriers
    assert "adrv9371" in cat.boards and "zc706" in cat.boards["adrv9371"].carriers
    assert "daq3" in cat.boards and "vcu118" in cat.boards["daq3"].carriers


def test_shipped_catalog_exposes_ad9371_chip_alias():
    """``--part ad9371`` (the chip name) must resolve to the adrv9371 board."""
    cat = load_catalog(str(SHIPPED_CATALOG))
    key, entry = cat.lookup("ad9371")
    assert key == "adrv9371"
    assert "ad9371" in entry.aliases


def test_shipped_catalog_flash_capable_boards():
    """adrv9009 + adrv9371 advertise no-os flash support (BootNoOSJTAG) and
    point at their no-os project dir under projects/."""
    cat = load_catalog(str(SHIPPED_CATALOG))
    for part, proj in (("adrv9009", "adrv9009"), ("adrv9371", "ad9371")):
        fl = cat.boards[part].flash
        assert fl is not None, f"{part} should advertise flash support"
        assert fl.strategy == "BootNoOSJTAG"
        assert fl.noos_project == proj


def test_shipped_catalog_images_are_pinned_not_placeholders():
    """Every shipped entry that pins an image uses a real KuiperRelease
    version, never a ``kuiper-...`` placeholder (a placeholder would break a
    real boot). Boards that boot via fabric load (e.g. daq3) carry no image."""
    cat = load_catalog(str(SHIPPED_CATALOG))
    for name, entry in cat.boards.items():
        if entry.image is None:
            continue
        assert not entry.image.startswith("kuiper-"), (
            f"{name!r} image is a placeholder: {entry.image!r}"
        )
