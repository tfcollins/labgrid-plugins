from __future__ import annotations

from types import SimpleNamespace

import pytest

from adi_lg_plugins.pytest_plugin import _board_sources, adi_board, adi_uri


def _raw(fixture):
    """The underlying function of a @pytest.fixture-decorated object."""
    # pytest >= 9 uses __wrapped__; older builds used __pytest_wrapped__.obj
    if hasattr(fixture, "__pytest_wrapped__"):
        return fixture.__pytest_wrapped__.obj
    return fixture.__wrapped__


def _cfg(**opts):
    """Fake pytest config: getoption(name) returns opts.get(name)."""
    return SimpleNamespace(getoption=lambda name: opts.get(name))


# ---- _board_sources precedence (pure) ----


def test_board_sources_options_win_over_env():
    uri, part, carrier, coord = _board_sources(
        _cfg(adi_uri="ip:opt", adi_part="p_opt", adi_carrier="c_opt").getoption,
        {
            "IIO_URI": "ip:env",
            "ADI_PART": "p_env",
            "ADI_CARRIER": "c_env",
            "LG_COORDINATOR": "coord:8000",
        },
    )
    assert (uri, part, carrier, coord) == ("ip:opt", "p_opt", "c_opt", "coord:8000")


def test_board_sources_falls_back_to_env():
    uri, part, carrier, coord = _board_sources(
        _cfg().getoption,
        {"IIO_URI": "ip:env", "ADI_PART": "p_env", "ADI_CARRIER": "c_env"},
    )
    assert (uri, part, carrier) == ("ip:env", "p_env", "c_env")
    assert coord is None


def test_board_sources_coord_alt_env_name():
    _, _, _, coord = _board_sources(_cfg().getoption, {"ADI_LG_COORDINATOR": "alt:8000"})
    assert coord == "alt:8000"


# ---- adi_board / adi_uri fixture glue (driven directly, no pytester) ----


def test_adi_board_reuse_yields_lease(monkeypatch):
    monkeypatch.setenv("IIO_URI", "ip:1.2.3.4")
    monkeypatch.delenv("ADI_PART", raising=False)
    monkeypatch.delenv("ADI_CARRIER", raising=False)
    gen = _raw(adi_board)(_cfg())
    lease = next(gen)
    assert lease.uri == "ip:1.2.3.4"
    assert lease.place == ""
    with pytest.raises(StopIteration):  # teardown; reuse path releases nothing
        next(gen)


def test_adi_board_skips_when_no_source(monkeypatch):
    monkeypatch.delenv("IIO_URI", raising=False)
    monkeypatch.delenv("ADI_PART", raising=False)
    monkeypatch.delenv("ADI_CARRIER", raising=False)
    gen = _raw(adi_board)(_cfg())
    with pytest.raises(pytest.skip.Exception):
        next(gen)


def test_adi_uri_returns_board_uri():
    fake_board = SimpleNamespace(uri="ip:9.9.9.9")
    assert _raw(adi_uri)(fake_board) == "ip:9.9.9.9"
