from __future__ import annotations

import json
import subprocess
from importlib.metadata import entry_points
from pathlib import Path
from types import SimpleNamespace

import pytest

from adi_lg_plugins.prism import LabgridSessionHook, capture
from adi_lg_plugins.prism import session_hook as hook_module


def _context(tmp_path: Path, **config_overrides):
    config = {
        "labgrid_place": "board-1",
        "no_labgrid": False,
        "dmesg_via": "auto",
        "dmesg_ssh_user": "root",
        "dmesg_ssh_key": None,
    }
    config.update(config_overrides)
    return SimpleNamespace(
        hook_dir=tmp_path,
        config=SimpleNamespace(**config),
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
    )


def test_installed_distribution_registers_prism_session_hook():
    hooks = {entry.name: entry for entry in entry_points(group="pytest_prism.session_hooks")}
    assert hooks["labgrid"].load() is LabgridSessionHook


def test_session_pre_records_allowlisted_context(tmp_path, monkeypatch):
    monkeypatch.setenv("LG_COORDINATOR", "coordinator.example:20408")
    monkeypatch.setenv("LG_ENV", "/workspace/generated/board-1.yaml")
    monkeypatch.setenv("IIO_URI", "ip:user:secret@192.0.2.10?token=hidden")
    monkeypatch.setattr(
        hook_module,
        "fetch_raw_places",
        lambda *args, **kwargs: [
            {
                "name": "board-1",
                "comment": "rack 2",
                "acquired": "ci/user",
                "tags": {
                    "carrier": "zcu102",
                    "daughter-board": "ad9081",
                    "boot-strategy": "BootFPGASoC",
                    "secret-token": "do-not-report",
                },
                "matches": [
                    {"exporter": "nemo", "params": {"password": "do-not-report"}},
                ],
            }
        ],
    )
    monkeypatch.setattr(
        hook_module,
        "capture_dmesg_ssh",
        lambda *args, **kwargs: capture.CaptureResult(True, b"old\n", "ssh"),
    )

    result = LabgridSessionHook().session_pre(_context(tmp_path))

    assert result["tags"] == {
        "carrier": "zcu102",
        "daughter-board": "ad9081",
        "boot-strategy": "BootFPGASoC",
    }
    assert result["exporters"] == ["nemo"]
    assert result["acquired"] is True
    assert "comment" not in result
    assert result["coordinator_configured"] is True
    assert result["iio_uri"] == "ip:192.0.2.10"
    assert result["dmesg_pre_via"] == "ssh"
    assert (tmp_path / "dmesg_pre.log").read_bytes() == b"old\n"
    serialized = (tmp_path / "metadata.json").read_text()
    assert "secret" not in serialized
    assert json.loads(serialized) == result


def test_session_requires_explicit_place(tmp_path, monkeypatch):
    monkeypatch.setenv("LG_PLACE", "must-not-be-used")
    result = LabgridSessionHook().session_pre(_context(tmp_path, labgrid_place=None))
    assert result == {"enabled": False, "reason": "no explicit place selected"}


def test_metadata_failure_does_not_block_reporting(tmp_path, monkeypatch):
    monkeypatch.setenv("LG_COORDINATOR", "coordinator.example:20408")
    monkeypatch.setattr(
        hook_module,
        "fetch_raw_places",
        lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("fetch", 5)),
    )
    result = LabgridSessionHook().session_pre(_context(tmp_path, dmesg_via="none"))
    assert result["metadata_status"] == "unavailable"
    assert (tmp_path / "metadata.json").exists()


def test_no_labgrid_disables_all_capture(tmp_path, monkeypatch):
    called = False

    def fail_capture(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError

    monkeypatch.setattr(hook_module, "capture_dmesg_ssh", fail_capture)
    hook = LabgridSessionHook()
    ctx = _context(tmp_path, no_labgrid=True)
    assert hook.session_pre(ctx) == {"enabled": False, "reason": "disabled"}
    assert hook.session_post(ctx) == {"enabled": False, "reason": "disabled"}
    assert called is False


def test_session_captures_pre_post_diff_and_console_logs(tmp_path, monkeypatch):
    source = tmp_path / "lg-log"
    source.mkdir()
    (source / "console_main_serial").write_bytes(b"boot output\n")
    monkeypatch.setenv("PRISM_LABGRID_LOG_DIR", str(source))
    monkeypatch.setattr(hook_module, "_safe_place_metadata", lambda *args: {})
    captures = iter(
        [
            capture.CaptureResult(True, b"a\ndup\ndup\n", "ssh"),
            capture.CaptureResult(True, b"a\ndup\ndup\nnew\n", "ssh"),
        ]
    )
    monkeypatch.setattr(hook_module, "capture_dmesg_ssh", lambda *args, **kwargs: next(captures))

    hook = LabgridSessionHook()
    ctx = _context(tmp_path / "out")
    pre = hook.session_pre(ctx)
    post = hook.session_post(ctx)

    assert pre["dmesg_pre_via"] == "ssh"
    assert post["dmesg_post_via"] == "ssh"
    assert post["console_logs"] == ["console_main_serial.log"]
    assert (ctx.hook_dir / "dmesg_diff.log").read_bytes() == b"new\n"
    assert (ctx.hook_dir / "console_main_serial.log").read_bytes() == b"boot output\n"


def test_auto_reports_console_log_fallback(tmp_path, monkeypatch):
    source = tmp_path / "lg-log"
    source.mkdir()
    (source / "console_main").write_bytes(b"uart\n")
    monkeypatch.setenv("PRISM_LABGRID_LOG_DIR", str(source))
    monkeypatch.setattr(hook_module, "_safe_place_metadata", lambda *args: {})
    monkeypatch.setattr(
        hook_module,
        "capture_dmesg_ssh",
        lambda *args, **kwargs: capture.CaptureResult(False, b"", "ssh", "exit 255"),
    )
    hook = LabgridSessionHook()
    ctx = _context(tmp_path / "out")
    hook.session_pre(ctx)
    result = hook.session_post(ctx)
    assert result["fallback"] == "console_logs"
    assert result["console_logs"] == ["console_main.log"]


def test_console_mode_requires_existing_labgrid_logs(tmp_path, monkeypatch):
    result = LabgridSessionHook().session_post(_context(tmp_path, dmesg_via="console"))
    assert "set PRISM_LABGRID_LOG_DIR" in result["error"]


def test_console_copy_rejects_symlinks_and_tails_large_files(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    secret = tmp_path / "secret"
    secret.write_bytes(b"secret")
    (source / "console_leak").symlink_to(secret)
    large = source / "console_large"
    large.write_bytes(b"prefix" + b"x" * (capture.MAX_LOG_BYTES + 10))

    copied = capture.copy_console_logs(source, destination)

    assert copied == ["console_large.log"]
    assert not (destination / "console_leak.log").exists()
    assert (destination / "console_large.log").stat().st_size == capture.MAX_LOG_BYTES
    assert not (destination / "console_large.log").read_bytes().startswith(b"prefix")


def test_console_copy_limits_file_count_and_aggregate_size(tmp_path, monkeypatch):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    monkeypatch.setattr(capture, "MAX_CONSOLE_FILES", 2)
    monkeypatch.setattr(capture, "MAX_CONSOLE_TOTAL_BYTES", 5)
    monkeypatch.setattr(capture, "MAX_LOG_BYTES", 4)
    for index in range(3):
        (source / f"console_{index}").write_bytes(b"abcdef")

    copied = capture.copy_console_logs(source, destination)

    assert copied == ["console_0.log", "console_1.log"]
    assert sum((destination / name).stat().st_size for name in copied) == 5
    assert not (destination / "console_2.log").exists()


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        (b"a\ndup\ndup\n", b"a\ndup\ndup\nnew\n", b"new\n"),
        (b"old1\nold2\nkeep\n", b"keep\nnew\n", b"new\n"),
        (b"old\n", b"wrapped\nnew\n", b"wrapped\nnew\n"),
    ],
)
def test_dmesg_delta_preserves_order_duplicates_and_wrap(before, after, expected):
    assert capture.dmesg_delta(before, after) == expected


def test_capture_dmesg_ssh_uses_fixed_argv_and_bounds_output(monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return SimpleNamespace(returncode=0, stdout=b"x" * (capture.MAX_LOG_BYTES + 5))

    monkeypatch.setattr(capture.shutil, "which", lambda name: "/usr/bin/ssh")
    monkeypatch.setattr(capture.subprocess, "run", fake_run)
    result = capture.capture_dmesg_ssh("ip:192.0.2.10", user="root", key="/safe/key")
    assert result.ok is True
    assert len(result.output) == capture.MAX_LOG_BYTES
    assert seen["argv"] == [
        "/usr/bin/ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "-i",
        "/safe/key",
        "root@192.0.2.10",
        "dmesg",
        "--color=never",
    ]


def test_capture_dmesg_ssh_rejects_option_like_host(monkeypatch):
    monkeypatch.setattr(capture.subprocess, "run", lambda *args, **kwargs: pytest.fail("ran ssh"))
    assert capture.capture_dmesg_ssh("ip:-oProxyCommand=bad").ok is False


def test_capture_timeout_does_not_expose_stderr(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            args[0], kwargs["timeout"], output=b"partial", stderr=b"secret"
        )

    monkeypatch.setattr(capture.shutil, "which", lambda name: "/usr/bin/ssh")
    monkeypatch.setattr(capture.subprocess, "run", fake_run)
    result = capture.capture_dmesg_ssh("ip:192.0.2.10")
    assert result.error == "timed out"
    assert result.output == b"partial"
    assert b"secret" not in result.output
