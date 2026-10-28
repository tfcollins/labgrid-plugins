import hashlib
import inspect
import io
import json
import re
import zipfile
from pathlib import Path

import pytest

from adi_lg_plugins.agents import download as agent
from adi_lg_plugins.drivers import kuiperdldriver


@pytest.fixture(autouse=True)
def _no_real_download(monkeypatch):
    """A cache miss would download (and extract) the multi-GB Kuiper image."""

    def refuse(*args, **kwargs):
        raise AssertionError("tried to download a real Kuiper release")

    monkeypatch.setattr(kuiperdldriver.Downloader, "releases", refuse)
    monkeypatch.setattr(kuiperdldriver.Downloader, "download", refuse)


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


@pytest.fixture
def home_and_cwd(monkeypatch, tmp_path):
    """A home directory for "~", and a separate, empty working directory."""
    home, work = tmp_path / "home", tmp_path / "work"
    home.mkdir()
    work.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(work)
    return home, work


def _cached_image(cache: Path, release="2023_R2_P1") -> Path:
    cache.mkdir(parents=True)
    img = cache / "image_2025-03-18-ADI-Kuiper-full.img"
    img.write_bytes(b"img")
    (cache / "cache_info.json").write_text(json.dumps({release: {"image_path": str(img)}}))
    return img


def test_a_tilde_cache_path_is_the_home_directory(home_and_cwd):
    home, work = home_and_cwd
    img = _cached_image(home / ".labgrid" / "kuiper_releases")

    got = kuiperdldriver.download_release_image("2023_R2_P1", "~/.labgrid/kuiper_releases/")

    assert Path(got) == img
    assert list(work.iterdir()) == []  # no directory named "~"


def test_the_download_goes_to_the_cache_not_the_working_directory(monkeypatch, home_and_cwd):
    home, work = home_and_cwd
    image = b"kuiper image"
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("kuiper.img", image)
    release = {
        "link": "https://downloads.test/kuiper.zip",
        "zipname": "kuiper.zip",
        "zipmd5": hashlib.md5(archive.getvalue()).hexdigest(),
        "imgname": "kuiper",
        "imgmd5": hashlib.md5(image).hexdigest(),
    }
    monkeypatch.setattr(kuiperdldriver.Downloader, "releases", lambda self, version: release)
    monkeypatch.setattr(
        kuiperdldriver.Downloader,
        "download",
        lambda self, url, fname: Path(fname).write_bytes(archive.getvalue()),
    )

    got = kuiperdldriver.download_release_image("2023_R2_P1", "~/cache")

    cache = home / "cache"
    assert Path(got) == cache / "kuiper.img"
    assert Path(got).read_bytes() == image
    assert json.loads((cache / "cache_info.json").read_text())["2023_R2_P1"]["image_path"] == got
    assert sorted(p.name for p in cache.iterdir()) == ["cache_info.json", "kuiper.img"]
    assert list(work.iterdir()) == []  # nothing downloaded or extracted here


def _driver(cache_path):
    """The driver as the exporter-side agent builds it, from the client's resource config."""
    return agent._driver("kuiper", {"release_version": "2023_R2_P1", "cache_path": cache_path})


def test_the_driver_finds_a_cached_release_under_a_tilde_cache_path(home_and_cwd):
    home, work = home_and_cwd
    img = _cached_image(home / "kc")

    driver = _driver("~/kc")

    assert driver.check_cached() is True
    assert driver.get_full_image_path() == str(img)
    assert list(work.iterdir()) == []


def test_checking_an_empty_tilde_cache_creates_it_under_home(home_and_cwd):
    home, work = home_and_cwd

    assert _driver("~/kc").check_cached() is False

    assert (home / "kc").is_dir()
    assert list(work.iterdir()) == []


def test_the_cache_path_is_only_used_through_the_expanding_helper():
    """Every local use must expand "~"; the agent config passes it on as written, so it
    expands on the exporter host, in that user's home."""
    src = inspect.getsource(kuiperdldriver.KuiperDLDriver)
    # Only in _cache_path() itself and in _agent_config().
    uses = re.findall(r"(?:kuiper_)?resource\.cache_path", src)
    assert len(uses) == 2, "use self._cache_path() instead of kuiper_resource.cache_path"
