"""Fetch a board's HDL hardware export (``system_top.xsa``) from a Kuiper image.

The Kuiper SD image's boot FAT partition holds, per board+carrier, a folder
(e.g. ``zynq-zc706-adv7511-adrv9009/``) whose ``bootgen_sysfiles.tgz`` contains
the ``system_top.xsa`` Vivado hardware export a no-os build needs. This module
locates/downloads the Kuiper image for a release, finds the board's boot folder
in the FAT partition, extracts the ``.xsa``, and caches it — all without a
labgrid target, so the CI ``build-noos`` step can call it directly.

It reuses the download/cache logic in ``kuiperdldriver`` (the shared
``download_release_image`` free function) and the ``IMGFileExtractor``
FAT-partition reader.
"""

from __future__ import annotations

import fnmatch
import logging
import tarfile
from pathlib import Path

from ..drivers.imageextractor import IMGFileExtractor
from ..drivers.kuiperdldriver import download_release_image

logger = logging.getLogger(__name__)

# Where the raw Kuiper .img is cached (shared with the KuiperRelease default).
DEFAULT_IMAGE_CACHE = Path.home() / ".labgrid" / "kuiper_releases"
# Where extracted .xsa files are cached (<release>/<board>_<carrier>/system_top.xsa).
DEFAULT_XSA_CACHE = Path.home() / ".labgrid" / "kuiper_xsa"

BOOTGEN = "bootgen_sysfiles.tgz"
XSA_NAME = "system_top.xsa"


def ensure_kuiper_image(release: str, image_cache: str | None = None) -> Path:
    """Return the cached Kuiper ``.img`` for ``release``, downloading if absent."""
    cache_path = Path(image_cache or DEFAULT_IMAGE_CACHE)
    cache_path.mkdir(parents=True, exist_ok=True)
    return Path(download_release_image(release, str(cache_path), logger=logger))


def _find_fat_partition(ext: IMGFileExtractor) -> dict:
    for part in ext.get_partitions():
        if "FAT" in part.get("description", ""):
            return part
    raise RuntimeError("no FAT partition found in Kuiper image")


def _resolve_board_folder(entries: list[dict], *, board: str, carrier: str) -> str:
    """Return the boot folder name (no leading slash) matching
    ``*<carrier>*<board>*`` (case-insensitive) that contains
    ``bootgen_sysfiles.tgz``. Raise on 0 (FileNotFoundError) or >1 (ValueError)."""
    pat = f"*{carrier.lower()}*{board.lower()}*"
    tgz_parents = sorted(
        {
            str(Path(e["path"]).parent).lstrip("/")
            for e in entries
            if e.get("type") == "file" and Path(e["path"]).name == BOOTGEN
        }
    )
    matches = [p for p in tgz_parents if fnmatch.fnmatch(Path(p).name.lower(), pat)]
    if not matches:
        raise FileNotFoundError(
            f"no Kuiper boot folder matching '*{carrier}*{board}*' containing {BOOTGEN}; "
            f"candidates: {[Path(p).name for p in tgz_parents]}"
        )
    if len(matches) > 1:
        raise ValueError(
            f"ambiguous Kuiper boot folder for {board}/{carrier}: "
            f"{[Path(m).name for m in matches]} — set flash.kuiper_xsa_dir / --xsa-dir"
        )
    return matches[0]


def fetch_board_xsa(
    release: str,
    board: str,
    carrier: str,
    cache_dir: str | None = None,
    *,
    xsa_dir: str | None = None,
    image_cache: str | None = None,
) -> Path:
    """Resolve + cache the board's ``system_top.xsa`` from the Kuiper image.

    ``board`` is the canonical daughter-board (e.g. ``adrv9371``), ``carrier``
    the FPGA carrier (e.g. ``zc706``). ``xsa_dir`` pins the boot folder name and
    skips the FAT search. Returns the cached ``.xsa`` path."""
    out_dir = Path(cache_dir or DEFAULT_XSA_CACHE) / release / f"{board}_{carrier}"
    out_xsa = out_dir / XSA_NAME
    if out_xsa.exists():
        logger.info("cached .xsa for %s/%s at %s", board, carrier, out_xsa)
        return out_xsa

    img = ensure_kuiper_image(release, image_cache=image_cache)
    ext = IMGFileExtractor(str(img), logger=logger)
    try:
        fat = _find_fat_partition(ext)
        fs = ext.open_filesystem(fat["start"])
        entries = ext.list_files(fs, "/")
        folder = (
            xsa_dir.strip("/")
            if xsa_dir
            else _resolve_board_folder(entries, board=board, carrier=carrier)
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        tgz_path = out_dir / BOOTGEN
        if not ext.extract_file(fs, f"/{folder}/{BOOTGEN}", str(tgz_path)):
            raise FileNotFoundError(f"failed to extract /{folder}/{BOOTGEN} from Kuiper image")
    finally:
        ext.close()

    with tarfile.open(tgz_path) as tf:
        member = next((m for m in tf.getmembers() if Path(m.name).name == XSA_NAME), None)
        if member is None:
            raise FileNotFoundError(f"{BOOTGEN} for {board}/{carrier} has no {XSA_NAME}")
        member.name = XSA_NAME  # flatten any internal path
        tf.extract(member, out_dir)

    logger.info("extracted .xsa for %s/%s to %s", board, carrier, out_xsa)
    return out_xsa
