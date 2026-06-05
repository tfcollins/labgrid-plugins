import io
import tarfile
from pathlib import Path

import pytest

from adi_lg_plugins.hw_ci import kuiper_xsa


def test_resolve_board_folder_unique_match():
    entries = [
        {"path": "/zynq-zc706-adv7511-adrv9009", "type": "dir", "size": 0},
        {"path": "/zynq-zc706-adv7511-adrv9009/bootgen_sysfiles.tgz", "type": "file", "size": 9},
        {"path": "/zynq-zc706-adv7511-adrv9371", "type": "dir", "size": 0},
        {"path": "/zynq-zc706-adv7511-adrv9371/bootgen_sysfiles.tgz", "type": "file", "size": 9},
    ]
    assert (
        kuiper_xsa._resolve_board_folder(entries, board="adrv9009", carrier="zc706")
        == "zynq-zc706-adv7511-adrv9009"
    )


def test_resolve_board_folder_no_match_lists_candidates():
    entries = [
        {"path": "/zynq-zc706-adv7511-adrv9371/bootgen_sysfiles.tgz", "type": "file", "size": 9},
    ]
    with pytest.raises(FileNotFoundError) as e:
        kuiper_xsa._resolve_board_folder(entries, board="ad9081", carrier="zcu102")
    assert "zynq-zc706-adv7511-adrv9371" in str(e.value)


def test_resolve_board_folder_ambiguous():
    entries = [
        {"path": "/a-zc706-adrv9009/bootgen_sysfiles.tgz", "type": "file", "size": 9},
        {"path": "/b-zc706-adrv9009/bootgen_sysfiles.tgz", "type": "file", "size": 9},
    ]
    with pytest.raises(ValueError) as e:
        kuiper_xsa._resolve_board_folder(entries, board="adrv9009", carrier="zc706")
    assert "ambiguous" in str(e.value).lower()


def test_fetch_board_xsa_cache_hit_skips_extraction(tmp_path, monkeypatch):
    cache_dir = tmp_path / "xsa"
    out = cache_dir / "2023_R2_P1" / "adrv9009_zc706" / "system_top.xsa"
    out.parent.mkdir(parents=True)
    out.write_bytes(b"cached")

    def _boom(*a, **k):
        raise AssertionError("must not download/extract on cache hit")

    monkeypatch.setattr(kuiper_xsa, "ensure_kuiper_image", _boom)

    got = kuiper_xsa.fetch_board_xsa("2023_R2_P1", "adrv9009", "zc706", cache_dir=str(cache_dir))
    assert got == out


def test_fetch_board_xsa_extracts_from_tgz(tmp_path, monkeypatch):
    cache_dir = tmp_path / "xsa"

    def fake_extract_file(fs, file_path, output_path):
        assert file_path.endswith("/bootgen_sysfiles.tgz")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(output_path, "w:gz") as tf:
            data = b"XSA-BYTES"
            info = tarfile.TarInfo("system_top.xsa")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        return True

    class FakeExtractor:
        def __init__(self, img_path, logger=None):
            pass

        def get_partitions(self):
            return [{"description": "FAT (0x0c)", "start": 12582912}]

        def open_filesystem(self, offset):
            return object()

        def list_files(self, fs, path="/"):
            return [
                {"path": "/zynq-zc706-adv7511-adrv9009", "type": "dir", "size": 0},
                {
                    "path": "/zynq-zc706-adv7511-adrv9009/bootgen_sysfiles.tgz",
                    "type": "file",
                    "size": 9,
                },
            ]

        extract_file = staticmethod(fake_extract_file)

        def close(self):
            pass

    monkeypatch.setattr(kuiper_xsa, "ensure_kuiper_image", lambda *a, **k: tmp_path / "k.img")
    monkeypatch.setattr(kuiper_xsa, "IMGFileExtractor", FakeExtractor)

    out = kuiper_xsa.fetch_board_xsa("2023_R2_P1", "adrv9009", "zc706", cache_dir=str(cache_dir))
    assert out.read_bytes() == b"XSA-BYTES"
    assert out.name == "system_top.xsa"
