"""Unit tests for ``ci/discover_places.py``.

Exercises the pure dispatch logic against canned coordinator payloads,
plus the GHA output writers via ``tmp_path``-backed env vars. The
``fetch_places`` HTTP path is tested by monkeypatching ``urlopen``.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from ci import discover_places as dp  # noqa: E402

DISPATCH = {
    "zc706": {
        "lg_env": "examples/zynq7000_recovery/lg_zc706_recovery.yaml",
        "tests": ["tests/test_zynq7000_recovery_hw.py"],
        "runner_labels": ["self-hosted", "lab", "zc706"],
    },
    "zcu102": {
        "lg_env": "examples/lg_ad9081_zcu102_exporter.yaml",
        "tests": ["tests/coordinator/test_soc_strat_coordinator.py"],
        "runner_labels": ["self-hosted", "lab", "zcu102"],
        "python_version": "3.11",
    },
}


def _place(name, *, carrier=None, acquired=None):
    tags = {"carrier": carrier} if carrier else {}
    return {"name": name, "tags": tags, "acquired": acquired}


def test_dispatch_empty_places():
    matrix, skipped = dp.dispatch([], DISPATCH)
    assert matrix == []
    assert skipped == []


def test_dispatch_happy_path_includes_runner_labels_and_default_python():
    matrix, skipped = dp.dispatch([_place("rack1", carrier="zc706")], DISPATCH)
    assert skipped == []
    assert matrix == [
        {
            "place": "rack1",
            "carrier": "zc706",
            "lg_env": "examples/zynq7000_recovery/lg_zc706_recovery.yaml",
            "tests": ["tests/test_zynq7000_recovery_hw.py"],
            "runner_labels": ["self-hosted", "lab", "zc706"],
            "python_version": "3.12",
        }
    ]


def test_dispatch_honors_python_version_override():
    matrix, _ = dp.dispatch([_place("mini2", carrier="zcu102")], DISPATCH)
    assert matrix[0]["python_version"] == "3.11"


def test_dispatch_skips_acquired_places():
    matrix, skipped = dp.dispatch(
        [_place("rack1", carrier="zc706", acquired="ci-host/runner-1")], DISPATCH
    )
    assert matrix == []
    assert skipped == [("rack1", "zc706", "acquired by ci-host/runner-1")]


def test_dispatch_skips_untagged_places():
    matrix, skipped = dp.dispatch([_place("loose")], DISPATCH)
    assert matrix == []
    assert skipped == [("loose", None, "no carrier tag")]


def test_dispatch_skips_unknown_carrier():
    matrix, skipped = dp.dispatch([_place("future", carrier="newchip")], DISPATCH)
    assert matrix == []
    assert skipped == [("future", "newchip", "no entry in ci/hardware_targets.yml")]


def test_dispatch_mixed_set_keeps_only_runnable():
    places = [
        _place("rack1", carrier="zc706"),
        _place("loose"),
        _place("busy", carrier="zcu102", acquired="someone/else"),
        _place("future", carrier="newchip"),
        _place("mini2", carrier="zcu102"),
    ]
    matrix, skipped = dp.dispatch(places, DISPATCH)
    assert [m["place"] for m in matrix] == ["rack1", "mini2"]
    assert {s[0] for s in skipped} == {"loose", "busy", "future"}


def test_format_summary_lists_dispatched_and_skipped():
    matrix, skipped = dp.dispatch(
        [
            _place("rack1", carrier="zc706"),
            _place("loose"),
            _place("busy", carrier="zcu102", acquired="x/y"),
        ],
        DISPATCH,
    )
    out = dp.format_summary("http://coord:8000", matrix, skipped)
    assert "## Hardware-test discovery" in out
    assert "dispatched: 1 place(s)" in out
    assert "`rack1` (zc706)" in out
    assert "skipped: 2 place(s)" in out
    assert "`loose` (untagged)" in out
    assert "`busy` (carrier=zcu102): acquired by x/y" in out


def test_write_outputs_appends_to_github_output(tmp_path, monkeypatch):
    out_path = tmp_path / "out"
    out_path.write_text("preexisting=1\n")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_path))
    matrix = [
        {
            "place": "rack1",
            "carrier": "zc706",
            "lg_env": "x.yaml",
            "tests": ["tests/test_x.py"],
            "runner_labels": ["self-hosted"],
            "python_version": "3.12",
        }
    ]
    dp.write_outputs(matrix)
    body = out_path.read_text()
    assert body.startswith("preexisting=1\n")
    assert "has_places=true\n" in body
    [matrix_line] = [ln for ln in body.splitlines() if ln.startswith("matrix=")]
    parsed = json.loads(matrix_line.removeprefix("matrix="))
    assert parsed == {"include": matrix}


def test_write_outputs_has_places_false_on_empty(tmp_path, monkeypatch):
    out_path = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_path))
    dp.write_outputs([])
    body = out_path.read_text()
    assert "matrix=" + json.dumps({"include": []}) in body
    assert "has_places=false" in body


def test_write_summary_falls_back_to_stdout_without_env(capsys, monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    dp.write_summary("hello\n")
    assert capsys.readouterr().out == "hello\n"


def test_load_dispatch_round_trips_yaml(tmp_path):
    path = tmp_path / "td.yml"
    path.write_text(
        "boards:\n"
        "  zc706:\n"
        "    lg_env: x.yaml\n"
        "    tests: [tests/test_x.py]\n"
        "    runner_labels: [self-hosted, zc706]\n"
    )
    boards = dp.load_dispatch(path)
    assert "zc706" in boards
    assert boards["zc706"]["tests"] == ["tests/test_x.py"]


def test_load_dispatch_rejects_non_mapping(tmp_path):
    path = tmp_path / "bad.yml"
    path.write_text("boards: [1, 2, 3]\n")
    with pytest.raises(ValueError, match="must be a mapping"):
        dp.load_dispatch(path)


def test_fetch_places_uses_api_endpoint(monkeypatch):
    called = {}

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(url, timeout=None):
        called["url"] = url
        called["timeout"] = timeout
        return _Resp(b'[{"name": "rack1", "tags": {"carrier": "zc706"}}]')

    monkeypatch.setattr(dp.urllib.request, "urlopen", fake_urlopen)
    places = dp.fetch_places("http://coord:8000/")
    assert called["url"] == "http://coord:8000/api/places"
    assert called["timeout"] == 15.0
    assert places == [{"name": "rack1", "tags": {"carrier": "zc706"}}]


def test_main_exits_2_when_api_url_missing(monkeypatch, capsys):
    monkeypatch.delenv("COORDINATOR_API_URL", raising=False)
    assert dp.main([]) == 2
    err = capsys.readouterr().err
    assert "COORDINATOR_API_URL" in err


def test_main_end_to_end_writes_matrix_and_summary(monkeypatch, tmp_path):
    monkeypatch.setenv("COORDINATOR_API_URL", "http://coord:8000")
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out"))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "sum"))
    monkeypatch.setattr(dp, "load_dispatch", lambda *a, **kw: DISPATCH)
    monkeypatch.setattr(
        dp,
        "fetch_places",
        lambda *a, **kw: [
            {"name": "rack1", "tags": {"carrier": "zc706"}, "acquired": None},
            {"name": "loose", "tags": {}, "acquired": None},
        ],
    )

    assert dp.main([]) == 0

    out = (tmp_path / "out").read_text()
    assert "has_places=true" in out
    assert '"place": "rack1"' in out
    summary = (tmp_path / "sum").read_text()
    assert "dispatched: 1 place(s)" in summary
    assert "`loose` (untagged): no carrier tag" in summary
