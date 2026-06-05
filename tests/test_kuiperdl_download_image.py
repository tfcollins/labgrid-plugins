import json
from pathlib import Path

from adi_lg_plugins.drivers import kuiperdldriver


def test_download_release_image_returns_cached_when_present(tmp_path):
    cache = tmp_path
    img = cache / "image_2025-03-18-ADI-Kuiper-full.img"
    img.write_bytes(b"img")
    (cache / "cache_info.json").write_text(json.dumps({"2023_R2_P1": {"image_path": str(img)}}))

    got = kuiperdldriver.download_release_image("2023_R2_P1", str(cache))
    assert Path(got) == img


def test_check_failure_message_has_no_typo():
    import inspect

    src = inspect.getsource(kuiperdldriver.Downloader.check)
    assert "FAILEDZz" not in src
    assert "MD5 Check: FAILED" in src


def test_no_dead_del_or_notimplemented():
    import inspect

    src = inspect.getsource(kuiperdldriver)
    assert "def __del__" not in src
    assert "NotImplementedError" not in src
