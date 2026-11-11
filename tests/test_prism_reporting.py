from __future__ import annotations

import json
import subprocess
from importlib.metadata import entry_points
from pathlib import Path
from types import SimpleNamespace

import pytest

from adi_lg_plugins.prism import LabgridSessionHook, capture
from adi_lg_plugins.prism import session_hook as hook_module


@pytest.fixture(autouse=True)
def _iio_environment(monkeypatch):
    monkeypatch.setenv("IIO_URI", "ip:192.0.2.10")
    monkeypatch.delenv("IIO_URI_OVERRIDE", raising=False)


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


def test_capture_dmesg_ssh_uses_fixed_argv_and_preserves_complete_output(monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return SimpleNamespace(returncode=0, stdout=b"x" * (capture.MAX_LOG_BYTES + 5))

    monkeypatch.setattr(capture.shutil, "which", lambda name: "/usr/bin/ssh")
    monkeypatch.setattr(capture.subprocess, "run", fake_run)
    result = capture.capture_dmesg_ssh("ip:192.0.2.10", user="root", key="/safe/key")
    assert result.ok is True
    assert len(result.output) == capture.MAX_LOG_BYTES + 5
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


def test_metadata_uses_acquired_resources_and_board_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("LG_COORDINATOR", "coordinator.example:20408")
    monkeypatch.setattr(
        hook_module,
        "fetch_raw_places",
        lambda *args, **kwargs: [
            {
                "name": "board-1",
                "acquired": "ci/user",
                "tags": {"daughter-board": "ad9081", "carrier": "zcu102"},
                "matches": [{"exporter": "wildcard-*"}],
                "acquired_resources": [["actual-exporter", "group", "NetworkService", "iio"]],
            }
        ],
    )
    result = LabgridSessionHook().session_pre(_context(tmp_path, dmesg_via="none"))
    assert result["board"] == "ad9081"
    assert result["carrier"] == "zcu102"
    assert result["exporter"] == "actual-exporter"
    assert result["exporters"] == ["actual-exporter"]
    assert result["metadata_status"] == "ok"


@pytest.mark.parametrize(
    "coordinator,places,error",
    [
        (None, [], "coordinator is not configured"),
        ("coordinator.example:20408", [], "selected place was not found"),
    ],
)
def test_missing_allocation_metadata_is_explicit(tmp_path, monkeypatch, coordinator, places, error):
    monkeypatch.delenv("ADI_LG_COORDINATOR", raising=False)
    monkeypatch.delenv("LG_COORDINATOR", raising=False)
    if coordinator:
        monkeypatch.setenv("LG_COORDINATOR", coordinator)
    monkeypatch.setattr(hook_module, "fetch_raw_places", lambda *args, **kwargs: places)
    result = LabgridSessionHook().session_pre(_context(tmp_path, dmesg_via="none"))
    assert result["metadata_status"] == "unavailable"
    assert result["metadata_error"] == error


def test_session_post_persists_capture_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(hook_module, "_safe_place_metadata", lambda *args: {})
    monkeypatch.setattr(
        hook_module,
        "capture_dmesg_ssh",
        lambda *args, **kwargs: capture.CaptureResult(False, b"", "ssh", "exit 255"),
    )
    hook = LabgridSessionHook()
    ctx = _context(tmp_path)
    hook.session_pre(ctx)
    post = hook.session_post(ctx)
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    assert metadata["dmesg_post_error"] == post["dmesg_post_error"] == "exit 255"
    assert metadata["dmesg_pre_error"] == "exit 255"


def test_runner_finalizes_artifacts_before_returning_failure(tmp_path, monkeypatch):
    import sys
    import zipfile

    from adi_lg_plugins.prism.run import main

    monkeypatch.setenv("LG_PLACE", "board-1")
    monkeypatch.setattr(hook_module, "_safe_place_metadata", lambda *args: {"board": "ad9081"})
    captures = iter(
        [
            capture.CaptureResult(True, b"before\n", "ssh"),
            capture.CaptureResult(True, b"before\nafter\n", "ssh"),
        ]
    )
    monkeypatch.setattr(hook_module, "capture_dmesg_ssh", lambda *args, **kwargs: next(captures))
    output = tmp_path / "report"
    rc = main(["--output-dir", str(output), "--", sys.executable, "-c", "raise SystemExit(7)"])
    assert rc == 7
    hardware = json.loads((output / "hardware.json").read_text())
    assert hardware["place"] == "board-1"
    assert hardware["board"] == "ad9081"
    with zipfile.ZipFile(output / "artifacts.zip") as archive:
        assert archive.read("hooks/labgrid/dmesg_diff.log") == b"after\n"
        assert archive.read("hooks/labgrid/dmesg_pre.log") == b"before\n"
        assert archive.read("hooks/labgrid/dmesg_post.log") == b"before\nafter\n"


def test_runner_retains_test_exit_status_when_collector_fails(tmp_path, monkeypatch):
    import sys

    from adi_lg_plugins.prism.run import main

    def broken_capture(self, ctx):
        raise PermissionError("private diagnostic")

    monkeypatch.setattr(LabgridSessionHook, "session_pre", broken_capture)
    monkeypatch.setattr(LabgridSessionHook, "session_post", broken_capture)
    output = tmp_path / "report"
    assert main(["--output-dir", str(output), "--", sys.executable, "-c", "exit(3)"]) == 3
    metadata = json.loads((output / "hardware.json").read_text())
    assert len(metadata["collection_errors"]) == 2
    assert "PermissionError" in metadata["collection_errors"][0]
    assert "private diagnostic" not in json.dumps(metadata)


def test_runner_preserves_failed_pipeline_transcript(tmp_path, monkeypatch):
    import shlex

    from adi_lg_plugins.prism.run import main

    monkeypatch.setenv("PRISM_DMESG_VIA", "none")
    monkeypatch.setenv("LG_PLACE", "board-1")
    monkeypatch.setattr(hook_module, "_safe_place_metadata", lambda *args: {})
    transcript = tmp_path / "pytest.log"
    pipeline = "{ echo stdout; echo stderr >&2; exit 4; } 2>&1 | tee " + shlex.quote(
        str(transcript)
    )
    output = tmp_path / "report"
    assert main(["--output-dir", str(output), "--", "bash", "-o", "pipefail", "-c", pipeline]) == 4
    assert transcript.read_text() == "stdout\nstderr\n"
    assert (output / "artifacts.zip").is_file()


@pytest.mark.parametrize("signal_name", ["SIGTERM", "SIGINT"])
def test_runner_forwards_signals_and_finalizes_before_exit(tmp_path, monkeypatch, signal_name):
    import os
    import selectors
    import signal
    import sys
    import zipfile

    monkeypatch.delenv("LG_COORDINATOR", raising=False)
    monkeypatch.delenv("ADI_LG_COORDINATOR", raising=False)
    monkeypatch.setenv("LG_PLACE", "signal-board")
    monkeypatch.setenv("PRISM_DMESG_VIA", "none")
    child_pid_file = tmp_path / "child.pid"
    grandchild_pid_file = tmp_path / "grandchild.pid"
    forwarded = tmp_path / "forwarded.txt"
    grandchild_code = f"""
import os, signal, time
from pathlib import Path
Path({str(grandchild_pid_file)!r}).write_text(str(os.getpid()))
def stopped(signum, frame):
    Path({str(forwarded)!r}).write_text(str(signum))
    raise SystemExit(128 + signum)
signal.signal(signal.SIGTERM, stopped)
signal.signal(signal.SIGINT, stopped)
print('READY', flush=True)
time.sleep(60)
"""
    child_code = f"""
import os, signal, subprocess, sys, time
from pathlib import Path
Path({str(child_pid_file)!r}).write_text(str(os.getpid()))
child = subprocess.Popen([sys.executable, '-c', {grandchild_code!r}], stdout=subprocess.PIPE, text=True)
def stopped(signum, frame):
    child.wait(timeout=3)
    raise SystemExit(128 + signum)
signal.signal(signal.SIGTERM, stopped)
signal.signal(signal.SIGINT, stopped)
child.stdout.readline()
print('READY', flush=True)
time.sleep(60)
"""
    output = tmp_path / "report"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "adi_lg_plugins.prism.run",
            "--output-dir",
            str(output),
            "--",
            sys.executable,
            "-c",
            child_code,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            assert selector.select(timeout=5), "runner child did not become ready"
        assert proc.stdout.readline().strip() == "READY"
        signum = getattr(signal, signal_name)
        proc.send_signal(signum)
        assert proc.wait(timeout=8) == 128 + signum
        assert forwarded.read_text() == str(signum)
        with pytest.raises(ProcessLookupError):
            os.kill(int(child_pid_file.read_text()), 0)
        with pytest.raises(ProcessLookupError):
            os.kill(int(grandchild_pid_file.read_text()), 0)
        metadata = json.loads((output / "hardware.json").read_text())
        assert metadata["place"] == "signal-board"
        with zipfile.ZipFile(output / "artifacts.zip") as archive:
            assert "hooks/labgrid/metadata.json" in archive.namelist()
    finally:
        for path in (grandchild_pid_file, child_pid_file):
            if path.exists():
                try:
                    os.kill(int(path.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)


def test_runner_clears_previous_capture_when_retry_collection_fails(tmp_path, monkeypatch):
    import sys
    import zipfile

    from adi_lg_plugins.prism.run import main

    monkeypatch.setenv("LG_PLACE", "board-1")
    monkeypatch.setattr(hook_module, "_safe_place_metadata", lambda *args: {})
    captures = iter(
        [
            capture.CaptureResult(True, b"previous board pre\n", "ssh"),
            capture.CaptureResult(True, b"previous board post\n", "ssh"),
            capture.CaptureResult(False, b"", "ssh", "exit 255"),
            capture.CaptureResult(False, b"", "ssh", "exit 255"),
        ]
    )
    monkeypatch.setattr(hook_module, "capture_dmesg_ssh", lambda *args, **kwargs: next(captures))
    output = tmp_path / "report"
    command = ["--output-dir", str(output), "--", sys.executable, "-c", "pass"]
    assert main(command) == 0
    assert (output / "hooks" / "labgrid" / "dmesg_pre.log").is_file()
    (output / "hooks" / "labgrid" / "console_previous.log").write_text("old console")
    monkeypatch.setenv("LG_PLACE", "board-2")
    assert main(command) == 0
    with zipfile.ZipFile(output / "artifacts.zip") as archive:
        assert all(
            "dmesg" not in name and "console_previous" not in name for name in archive.namelist()
        )
    assert not (output / "hooks" / "labgrid" / "dmesg_pre.log").exists()
    assert json.loads((output / "hardware.json").read_text())["place"] == "board-2"


def test_session_uses_verified_iio_override_for_metadata_and_dmesg(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setenv("IIO_URI", "ip:192.0.2.10")
    monkeypatch.setenv("IIO_URI_OVERRIDE", "ip:192.0.2.20")
    monkeypatch.setattr(hook_module, "_safe_place_metadata", lambda *args: {})
    monkeypatch.setattr(
        hook_module,
        "capture_dmesg_ssh",
        lambda uri, **kwargs: seen.append(uri) or capture.CaptureResult(True, b"dmesg\n", "ssh"),
    )
    hook = LabgridSessionHook()
    ctx = _context(tmp_path)
    result = hook.session_pre(ctx)
    hook.session_post(ctx)
    assert result["iio_uri"] == "ip:192.0.2.20"
    assert seen == ["ip:192.0.2.20", "ip:192.0.2.20"]


def test_session_resolves_live_uri_from_legacy_labgrid_environment(tmp_path, monkeypatch):
    import labgrid

    seen = []
    shell = SimpleNamespace(run=lambda command: (["192.0.2.30"], [], 0))
    target = SimpleNamespace(get_driver=lambda driver: shell)
    cleaned = []
    monkeypatch.delenv("IIO_URI", raising=False)
    monkeypatch.delenv("IIO_URI_OVERRIDE", raising=False)
    monkeypatch.setenv("LG_ENV", str(tmp_path / "reserved.yaml"))
    monkeypatch.setattr(
        labgrid,
        "Environment",
        lambda config: SimpleNamespace(
            get_target=lambda: target, cleanup=lambda: cleaned.append(True)
        ),
    )
    monkeypatch.setattr(hook_module, "_safe_place_metadata", lambda *args: {})
    monkeypatch.setattr(
        hook_module,
        "capture_dmesg_ssh",
        lambda uri, **kwargs: seen.append(uri) or capture.CaptureResult(True, b"dmesg\n", "ssh"),
    )
    result = LabgridSessionHook().session_pre(_context(tmp_path))
    assert seen == ["ip:192.0.2.30"]
    assert cleaned == [True]
    assert result["iio_uri"] == "ip:192.0.2.30"


def test_runner_waits_for_bash_pipeline_descendant_cleanup_before_capture(tmp_path, monkeypatch):
    import os
    import selectors
    import shlex
    import signal
    import sys

    monkeypatch.delenv("LG_COORDINATOR", raising=False)
    monkeypatch.delenv("ADI_LG_COORDINATOR", raising=False)
    monkeypatch.setenv("LG_PLACE", "pipeline-board")
    monkeypatch.setenv("PRISM_DMESG_VIA", "none")
    child_pid_file = tmp_path / "descendant.pid"
    finished = tmp_path / "finished"
    child_code = f"""
import os, signal, time
from pathlib import Path
Path({str(child_pid_file)!r}).write_text(str(os.getpid()))
def stopped(signum, frame):
    time.sleep(0.7)
    Path({str(finished)!r}).write_text('finished')
    raise SystemExit(128 + signum)
signal.signal(signal.SIGTERM, stopped)
print('READY', flush=True)
time.sleep(60)
"""
    driver_code = f"""
import sys
from pathlib import Path
from adi_lg_plugins.prism import run
original_post = run.LabgridSessionHook.session_post
def post(self, ctx):
    result = original_post(self, ctx)
    result['descendant_cleanup_finished'] = Path({str(finished)!r}).exists()
    return result
run.LabgridSessionHook.session_post = post
raise SystemExit(run.main(sys.argv[1:]))
"""
    pipeline = f"{shlex.quote(sys.executable)} -c {shlex.quote(child_code)} | tee {shlex.quote(str(tmp_path / 'pytest.log'))}"
    output = tmp_path / "report"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            driver_code,
            "--output-dir",
            str(output),
            "--",
            "bash",
            "-o",
            "pipefail",
            "-c",
            pipeline,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            assert selector.select(timeout=5), "pipeline did not become ready"
        assert proc.stdout.readline().strip() == "READY"
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=8) == 143
        metadata = json.loads((output / "hardware.json").read_text())
        assert metadata["descendant_cleanup_finished"] is True
        assert finished.is_file()
        with pytest.raises(ProcessLookupError):
            os.kill(int(child_pid_file.read_text()), 0)
        assert (output / "artifacts.zip").is_file()
    finally:
        if child_pid_file.exists():
            try:
                os.kill(int(child_pid_file.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)


def test_runner_kills_and_reaps_child_ignoring_term(tmp_path, monkeypatch):
    import os
    import selectors
    import signal
    import sys

    monkeypatch.delenv("LG_COORDINATOR", raising=False)
    monkeypatch.delenv("ADI_LG_COORDINATOR", raising=False)
    monkeypatch.setenv("LG_PLACE", "stubborn-child-board")
    monkeypatch.setenv("PRISM_DMESG_VIA", "none")
    pid_file = tmp_path / "child.pid"
    child_code = (
        "import os, signal, time; from pathlib import Path; "
        f"Path({str(pid_file)!r}).write_text(str(os.getpid())); "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "print('READY', flush=True); time.sleep(60)"
    )
    driver_code = (
        "import sys; from adi_lg_plugins.prism import run; "
        "run.PROCESS_GROUP_GRACE_SECONDS = 0.1; "
        "raise SystemExit(run.main(sys.argv[1:]))"
    )
    output = tmp_path / "report"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            driver_code,
            "--output-dir",
            str(output),
            "--",
            sys.executable,
            "-c",
            child_code,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            assert selector.select(timeout=5), "runner child did not become ready"
        assert proc.stdout.readline().strip() == "READY"
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=5) == 143
        with pytest.raises(ProcessLookupError):
            os.kill(int(pid_file.read_text()), 0)
        assert (output / "hardware.json").is_file()
        assert (output / "artifacts.zip").is_file()
    finally:
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_subreaper_falls_back_when_unavailable(monkeypatch, platform):
    from adi_lg_plugins.prism import run

    def unavailable(*args, **kwargs):
        raise OSError("native subreaper API unavailable")

    monkeypatch.setattr(run.sys, "platform", platform)
    monkeypatch.setattr(run.ctypes, "CDLL", unavailable)
    with run._child_subreaper():
        pass
