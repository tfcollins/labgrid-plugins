"""Unit tests for the shared RemoteExecMixin (drivers/_remote.py).

These exercise the three resource shapes the mixin must handle:

1. A local resource (test runner == exporter): no host, empty prefix, no
   file staging.
2. A plain ``Resource`` proxied from a coordinator: the exporter host lives
   only in ``resource.extra['proxy']`` (labgrid does not wrap custom
   resources in ``NetworkResource``). Commands route over ssh and files are
   staged via ``sshmanager``.
3. A genuine ``NetworkResource``: ``command_prefix`` is honored and staging
   delegates to labgrid's ``ManagedFile``.

sshmanager / ManagedFile are mocked so the suite runs without hardware or an
ssh server.
"""

import logging
import types
from unittest import mock

from labgrid.resource.common import NetworkResource

from adi_lg_plugins.drivers import _remote
from adi_lg_plugins.drivers._remote import RemoteExecMixin


class _FakeDriver(RemoteExecMixin):
    """Minimal driver-like object exposing a single bound resource as ``res``."""

    _remote_binding = "res"

    def __init__(self, res):
        self.res = res
        self.logger = logging.getLogger("test_remote_exec")


def _local_resource():
    # A plain resource with no host and no proxy => local execution.
    return types.SimpleNamespace(extra={})


def _proxied_resource(proxy="exp.example.com"):
    # A plain Resource proxied from a coordinator: host info only in extra.
    return types.SimpleNamespace(extra={"proxy": proxy})


def _network_resource(host="exp.example.com"):
    # A genuine NetworkResource instance (bypass attrs __init__).
    nr = NetworkResource.__new__(NetworkResource)
    nr.host = host
    nr.extra = {}
    return nr


# --- host resolution -------------------------------------------------------


def test_local_resource_is_not_remote():
    d = _FakeDriver(_local_resource())
    assert d._is_remote is False
    assert d._exporter_host(d._remote_resource()) is None


def test_proxied_resource_resolves_host_from_extra():
    d = _FakeDriver(_proxied_resource("exp.example.com"))
    assert d._is_remote is True
    assert d._exporter_host(d._remote_resource()) == "exp.example.com"


def test_network_resource_resolves_host_attr():
    d = _FakeDriver(_network_resource("nr.example.com"))
    assert d._exporter_host(d._remote_resource()) == "nr.example.com"
    assert d._is_remote is True


# --- command prefix --------------------------------------------------------


def test_local_prefix_is_empty():
    d = _FakeDriver(_local_resource())
    assert d._remote_prefix() == []


def test_proxied_prefix_built_from_sshmanager():
    d = _FakeDriver(_proxied_resource("exp.example.com"))
    fake_conn = mock.Mock()
    fake_conn.get_prefix.return_value = ["ssh", "-o", "x", "exp.example.com"]
    with mock.patch.object(_remote, "sshmanager") as sm:
        sm.get.return_value = fake_conn
        prefix = d._remote_prefix()
    sm.get.assert_called_once_with("exp.example.com")
    assert prefix == ["ssh", "-o", "x", "exp.example.com", "--"]


def test_network_resource_prefix_uses_command_prefix():
    nr = _network_resource()
    # Pretend command_prefix is already resolved by labgrid.
    with mock.patch.object(type(nr), "command_prefix", new=["ssh", "host", "--"]):
        d = _FakeDriver(nr)
        assert d._remote_prefix() == ["ssh", "host", "--"]


# --- command execution -----------------------------------------------------


def test_remote_run_local_prepends_no_prefix():
    d = _FakeDriver(_local_resource())
    with mock.patch.object(_remote.subprocess, "run") as run:
        run.return_value = mock.Mock(returncode=0)
        d._remote_run(["pmount", "/dev/sdb1"])
    run.assert_called_once()
    assert run.call_args[0][0] == ["pmount", "/dev/sdb1"]


def test_remote_run_remote_prepends_prefix():
    d = _FakeDriver(_proxied_resource("exp.example.com"))
    fake_conn = mock.Mock()
    fake_conn.get_prefix.return_value = ["ssh", "exp.example.com"]
    with (
        mock.patch.object(_remote, "sshmanager") as sm,
        mock.patch.object(_remote.subprocess, "run") as run,
    ):
        sm.get.return_value = fake_conn
        run.return_value = mock.Mock(returncode=0)
        d._remote_run(["pmount", "/dev/sdb1"])
    assert run.call_args[0][0] == ["ssh", "exp.example.com", "--", "pmount", "/dev/sdb1"]


def test_remote_check_raises_on_nonzero():
    # Local execution runs the real subprocess; ``false`` exits non-zero and
    # check=True must surface it as CalledProcessError.
    import subprocess

    import pytest

    d = _FakeDriver(_local_resource())
    with pytest.raises(subprocess.CalledProcessError):
        d._remote_check(["false"])


# --- file staging ----------------------------------------------------------


def test_stage_file_local_returns_input(tmp_path):
    f = tmp_path / "boot.scr"
    f.write_text("data")
    d = _FakeDriver(_local_resource())
    assert d._stage_file(str(f)) == str(f)


def test_stage_file_proxied_uploads_and_returns_remote_path(tmp_path):
    f = tmp_path / "boot.scr"
    f.write_text("data")
    d = _FakeDriver(_proxied_resource("exp.example.com"))
    fake_conn = mock.Mock()
    with mock.patch.object(_remote, "sshmanager") as sm:
        sm.get.return_value = fake_conn
        remote = d._stage_file(str(f))
    # A directory was created and the file pushed onto the exporter.
    fake_conn.run_check.assert_called()
    fake_conn.put_file.assert_called_once()
    local_arg, remote_arg = fake_conn.put_file.call_args[0]
    assert local_arg == str(f)
    assert remote.endswith("/boot.scr")
    assert remote == remote_arg


def test_stage_file_network_resource_uses_managedfile(tmp_path):
    f = tmp_path / "boot.scr"
    f.write_text("data")
    d = _FakeDriver(_network_resource("nr.example.com"))
    mf_instance = mock.Mock()
    mf_instance.get_remote_path.return_value = "/var/cache/abc/boot.scr"
    with mock.patch.object(_remote, "ManagedFile", return_value=mf_instance) as MF:
        remote = d._stage_file(str(f))
    MF.assert_called_once()
    mf_instance.sync_to_resource.assert_called_once()
    assert remote == "/var/cache/abc/boot.scr"
