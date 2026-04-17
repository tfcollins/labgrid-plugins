"""Session-scoped fixtures for hardware-tier coordinator tests.

Defined here so pytest honors scope="session" caching across test modules.
(Fixtures imported via `from X import Y` from a test module get module-local
identities, which caused session setup/teardown to re-run per module and
broke acquire/release when two modules shared the coordinator session.)
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

# ---------- hardware tier ----------


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _spawn_exporter(*, coord, host, name, yaml_path):
    """Launch labgrid-exporter on `host` (locally if `host` resolves to this
    machine; else via ssh). Blocks until the coordinator sees at least one
    resource published under `{name}/tlab/`.

    Returns a dict carrying enough state for _stop_exporter(): keys
    ``proc``, ``remote_yaml``, ``is_local``, ``host``.

    Raises pytest.skip/pytest.fail when preconditions are missing or the
    exporter doesn't register in time. Callers should pass the result to
    _stop_exporter() even on failure (the proc may still be running).
    """
    if not yaml_path.is_file():
        pytest.skip(f"exporter yaml missing: {yaml_path}")

    remote_yaml = f"/tmp/lg_exporter_{os.getpid()}_{name}.yaml"
    is_local = host in (socket.gethostname(), "localhost", "127.0.0.1")

    if is_local:
        shutil.copy(str(yaml_path), remote_yaml)
    else:
        try:
            subprocess.check_call(
                ["scp", "-q", str(yaml_path), f"{host}:{remote_yaml}"],
                timeout=15,
            )
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            pytest.skip(f"scp to {host} failed: {e}")

    exporter_bin = os.environ.get("LG_EXPORTER_BIN", "labgrid-exporter")
    env_path = (
        f"{os.path.expanduser('~/opt/ser2net-4.6.1/sbin')}:"
        f"{os.path.expanduser('~/.local/bin')}:"
        f"{os.path.expanduser('~/bin')}:/usr/local/bin:{os.environ.get('PATH', '')}"
    )

    if is_local:
        proc = subprocess.Popen(
            [exporter_bin, "-c", coord, "-n", name, remote_yaml],
            env={**os.environ, "PATH": env_path},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    else:
        remote_cmd = (
            f'exec env PATH="$HOME/opt/ser2net-4.6.1/sbin:$HOME/.local/bin:$HOME/bin:/usr/local/bin:$PATH" '
            f"{exporter_bin} -c {coord} -n {name} {remote_yaml}"
        )
        proc = subprocess.Popen(
            ["ssh", "-tt", "-o", "ServerAliveInterval=10", host, remote_cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

    state = {"proc": proc, "remote_yaml": remote_yaml, "is_local": is_local, "host": host}

    deadline = time.time() + 45
    required_prefix = f"{name}/tlab/"
    seen = False
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read() if proc.stdout else ""
            pytest.skip(
                f"remote labgrid-exporter exited early ({proc.returncode}) on {host}:\n{out}"
            )
        try:
            res = subprocess.check_output(
                ["labgrid-client", "-x", coord, "resources"],
                text=True,
                stderr=subprocess.STDOUT,
                timeout=5,
            )
            if required_prefix in res:
                seen = True
                break
        except subprocess.SubprocessError:
            pass
        time.sleep(0.5)
    if seen:
        time.sleep(2.0)
    else:
        _stop_exporter(state)
        pytest.fail(f"exporter '{name}' never appeared in coordinator within 45s")
    return state


def _stop_exporter(state):
    proc = state.get("proc")
    if proc is not None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    try:
        if state["is_local"]:
            subprocess.call(["rm", "-f", state["remote_yaml"]], timeout=5)
        else:
            subprocess.call(
                [
                    "ssh",
                    state["host"],
                    f"pkill -f '{state['remote_yaml']}'; rm -f {state['remote_yaml']}",
                ],
                timeout=10,
            )
    except subprocess.SubprocessError:
        pass


def _load_exporters_config(config_path):
    """Parse the multi-exporter sidecar yaml. Returns a list of dicts:
    [{name, host, yaml}, ...]. Raises pytest.skip on malformed input."""
    import yaml as _yaml

    with open(config_path) as f:
        cfg = _yaml.safe_load(f)
    entries = cfg.get("exporters") if isinstance(cfg, dict) else None
    if not isinstance(entries, list) or not entries:
        pytest.skip(f"{config_path} has no non-empty 'exporters:' list")
    for e in entries:
        for key in ("name", "host", "yaml"):
            if key not in e:
                pytest.skip(f"{config_path} entry missing '{key}': {e}")
    return entries


@pytest.fixture(scope="session")
def remote_exporters(request):
    """Provide the set of labgrid places available for the test session.

    Three modes, selected by environment:

    * ``LG_EXPORTERS_CONFIG=<yaml>`` — multi-exporter mode: spawn each
      exporter listed under ``exporters:`` for the duration of the session.
    * ``LG_EXPORTER_HOST`` (plus ``LG_EXPORTER_NAME`` and
      ``LG_EXPORTER_YAML``) — legacy single-exporter mode: spawn one
      exporter. All three must be set; there are no defaults.
    * Neither set — discovery mode: do not spawn anything; use whichever
      places are already registered on the coordinator (as reported by
      ``labgrid-client places``).

    Yields ``{place_name: host_or_None}``. ``host`` is the exporter host
    when this fixture spawned it; ``None`` means the place was
    pre-registered by an exporter this fixture did not launch.
    """
    if not request.config.getoption("--run-hardware"):
        pytest.skip("--run-hardware required")
    if not os.environ.get("LG_COORDINATOR"):
        pytest.skip("LG_COORDINATOR required")
    coord = os.environ["LG_COORDINATOR"]

    cfg_path = os.environ.get("LG_EXPORTERS_CONFIG")
    legacy_host = os.environ.get("LG_EXPORTER_HOST")

    if cfg_path:
        entries = _load_exporters_config(cfg_path)
    elif legacy_host:
        name = os.environ.get("LG_EXPORTER_NAME")
        yaml_rel = os.environ.get("LG_EXPORTER_YAML")
        if not (name and yaml_rel):
            pytest.skip("LG_EXPORTER_HOST set but LG_EXPORTER_NAME and/or LG_EXPORTER_YAML missing")
        entries = [{"name": name, "host": legacy_host, "yaml": yaml_rel}]
    else:
        ## Discovery mode: no spawn. Use whatever the coordinator already
        ## knows about. `labgrid-client places` prints one place per line.
        try:
            out = subprocess.check_output(
                ["labgrid-client", "-x", coord, "places"],
                text=True,
                stderr=subprocess.STDOUT,
                timeout=10,
            )
        except subprocess.SubprocessError as e:
            pytest.skip(f"could not query places on coordinator {coord}: {e}")
        places = [ln.strip() for ln in out.splitlines() if ln.strip()]
        if not places:
            pytest.skip(f"coordinator {coord} has no places registered")
        yield {p: None for p in places}
        return

    states = []
    try:
        for e in entries:
            states.append(
                _spawn_exporter(
                    coord=coord,
                    host=e["host"],
                    name=e["name"],
                    yaml_path=REPO_ROOT / e["yaml"],
                )
            )
        yield {e["name"]: e["host"] for e in entries}
    finally:
        for st in states:
            _stop_exporter(st)


@pytest.fixture(scope="session")
def remote_exporter(remote_exporters):
    """Backward-compatible singular: yields the first exporter name."""
    return next(iter(remote_exporters))


@pytest.fixture(scope="session")
def hw_targets(request, remote_exporters):
    """Acquire every labgrid Target in --lg-config whose RemotePlace matches
    a running exporter. Yields dict {remote_place_name: Target}.

    Session-scoped so all hardware tests share one labgrid client session
    (the gRPC client doesn't tolerate being torn down mid-session)."""
    lg_config = request.config.getoption("--lg-config")
    if not lg_config:
        pytest.skip("--lg-config required for hardware tests")
    if not Path(lg_config).is_file():
        pytest.skip(f"--lg-config path does not exist: {lg_config}")

    coord = os.environ["LG_COORDINATOR"]

    import yaml as _yaml

    with open(lg_config) as f:
        cfg = _yaml.safe_load(f)
    targets_cfg = (cfg or {}).get("targets", {})
    if not targets_cfg:
        pytest.skip("--lg-config has no targets")

    ## Map labgrid target name → RemotePlace.name in the env yaml.
    target_places = {}
    for tname, tcfg in targets_cfg.items():
        rp = (tcfg or {}).get("resources", {}).get("RemotePlace", {})
        place = rp.get("name") if isinstance(rp, dict) else None
        if place:
            target_places[tname] = place

    ## Reset RemotePlaceManager singleton so it picks up the hardware
    ## coordinator URL (smoke fixtures may have pinned it to 127.0.0.1).
    from labgrid.resource.common import ResourceManager

    ResourceManager.instances.clear()

    acquired = []
    targets = {}
    try:
        for _tname, place in target_places.items():
            if place not in remote_exporters:
                ## No running exporter for this place; skip silently so a
                ## merged env yaml can cover more places than spawned.
                continue
            subprocess.check_call(
                ["labgrid-client", "-x", coord, "-p", place, "acquire"],
                timeout=15,
            )
            acquired.append(place)

        from labgrid import Environment

        env = Environment(lg_config)
        for tname, place in target_places.items():
            if place not in remote_exporters:
                continue
            t = env.get_target(tname)
            if t is None:
                continue
            targets[place] = t

        yield targets
    finally:
        for place in acquired:
            try:
                subprocess.check_call(
                    ["labgrid-client", "-x", coord, "-p", place, "release"],
                    timeout=15,
                )
            except subprocess.SubprocessError:
                pass


@pytest.fixture(scope="session")
def hw_target(hw_targets):
    """Backward-compatible singular: returns the sole acquired target, or
    the one named by LG_EXPORTER_NAME when multiple are present."""
    if not hw_targets:
        pytest.skip("no hardware targets available")
    if len(hw_targets) == 1:
        return next(iter(hw_targets.values()))
    preferred = os.environ.get("LG_EXPORTER_NAME")
    if preferred and preferred in hw_targets:
        return hw_targets[preferred]
    pytest.skip(
        f"multiple hardware targets active ({list(hw_targets)}); set LG_EXPORTER_NAME "
        "to pick one, or have the test module override `hw_target` via `hw_targets[...]`"
    )


# ---------- shared strategy-test helpers ----------


@pytest.fixture(scope="module")
def in_shell(boot_strategy):
    """Drive ``boot_strategy`` to ``shell`` for the module, soft_off on
    teardown. Each test module provides its own ``boot_strategy`` fixture;
    this composes with whichever one is in scope.

    Named ``boot_strategy`` (not ``strategy``) to avoid clashing with
    labgrid's pytestplugin built-in, whose collection hook errors when
    --lg-env isn't set."""
    boot_strategy.transition("shell")
    yield boot_strategy
    boot_strategy.transition("soft_off")


def assert_linux_uname(hw_target):
    """Run `uname -a` via ADIShellDriver and assert the DUT is Linux."""
    shell = hw_target.get_driver("ADIShellDriver")
    stdout, stderr, returncode = shell.run("uname -a")
    assert returncode == 0, f"uname failed (rc={returncode}): {stderr}"
    assert any("Linux" in line for line in stdout), stdout


def assert_bindings_populated(strategy, names):
    """Assert each named binding on a labgrid strategy is non-None."""
    for name in names:
        assert getattr(strategy, name) is not None, f"binding '{name}' unbound"
