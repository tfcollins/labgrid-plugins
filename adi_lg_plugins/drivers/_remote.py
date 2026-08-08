"""Shared remote-execution helper for host-side drivers.

Some drivers in this package run work on the *exporter host* rather than on
the test runner or the DUT: :class:`XilinxJTAGDriver` invokes ``xsdb`` and
:class:`MassStorageDriver` runs ``pmount``/``pumount`` and copies files. When
the test runner is also the exporter, those commands run locally; when a
client acquires the place through a coordinator, they must run on the exporter
over ssh.

``RemoteExecMixin`` centralizes that "am I remote, and how do I reach the
exporter" decision so every host-side driver resolves it the same way, keyed
off its *own* bound resource, and reuses a single ssh ControlMaster (via
labgrid's ``sshmanager``) instead of spawning a fresh ``ssh`` per command.

Why ``extra['proxy']`` matters: the ADI resources (``MassStorageDevice``,
``XilinxDeviceJTAG``, ...) are plain :class:`labgrid.resource.common.Resource`
subclasses with no ``Network*`` variant. When proxied through a coordinator,
labgrid reconstructs them *as plain Resources* — it does not set ``host`` and
does not wrap them in :class:`~labgrid.resource.common.NetworkResource`. The
exporter records its host only in ``resource.extra['proxy']`` (see
``labgrid/remote/exporter.py`` and ``labgrid/resource/remote.py``). So the
exporter host is resolved as ``resource.host or resource.extra['proxy']``.

Known limitation: file staging opens a *direct* ssh to the resolved host
(matching the previous ``scp src host:dst`` behavior). Fully isolated
exporters that require a ProxyJump (``extra['proxy_required']`` true) are not a
target of this helper — that matches prior behavior.
"""

import hashlib
import os
import socket
import subprocess

from labgrid.resource.common import NetworkResource
from labgrid.util.managedfile import ManagedFile
from labgrid.util.ssh import sshmanager

_STAGE_ROOT = "/tmp/adi-lg-stage"

#: host -> resolvable form, memoized (DNS probes are slow and per-run stable).
_RESOLVED_HOSTS: dict[str, str] = {}


def _resolvable_host(host: str) -> str:
    """Return ``host`` in a form the local resolver can actually resolve.

    The coordinator names exporter hosts by bare name (e.g. ``tron``); on many
    lab networks only the mDNS ``<name>.local`` form resolves. Mirror
    ``hw_ci.all_places.host_reachable``: keep the bare name when it resolves,
    fall back to ``<name>.local`` when only that resolves, and otherwise return
    the input unchanged so the eventual ssh error names the real host.
    """
    cached = _RESOLVED_HOSTS.get(host)
    if cached is not None:
        return cached
    resolved = host
    for candidate in (host, f"{host}.local"):
        try:
            socket.getaddrinfo(candidate, None)
            resolved = candidate
            break
        except OSError:
            continue
    _RESOLVED_HOSTS[host] = resolved
    return resolved


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class RemoteExecMixin:
    """Mixin giving a driver uniform local-or-remote command/file execution.

    Subclasses set ``_remote_binding`` to the name of the bound resource that
    locates the exporter (e.g. ``"mass_storage"`` or ``"xilinxdevicejtag"``).
    The mixin carries no attrs fields, so it composes cleanly with the attrs
    ``Driver`` subclasses; declare it first in the MRO::

        class FooDriver(RemoteExecMixin, Driver):
            _remote_binding = "mass_storage"
    """

    #: Name of the bound resource used to locate the exporter host.
    _remote_binding: str = ""

    def _remote_resource(self):
        """Return the bound resource that locates the exporter host."""
        if not self._remote_binding:
            raise AttributeError(
                f"{type(self).__name__} must set _remote_binding to use RemoteExecMixin"
            )
        return getattr(self, self._remote_binding)

    @staticmethod
    def _exporter_host(res):
        """Resolve the exporter host for ``res``, or None for local execution.

        A genuine NetworkResource exposes ``host`` directly; a plain Resource
        proxied from a coordinator carries it in ``extra['proxy']``.
        """
        host = getattr(res, "host", None)
        if host:
            return _resolvable_host(host)
        extra = getattr(res, "extra", None) or {}
        if isinstance(extra, dict):
            proxy = extra.get("proxy")
            return _resolvable_host(proxy) if proxy else None
        return None

    def _remote_prefix(self):
        """Build the command prefix (empty list when local).

        Honors a genuine NetworkResource's own ``command_prefix``; otherwise
        builds one from a reused ssh connection to the resolved host.
        """
        res = self._remote_resource()
        prefix = list(getattr(res, "command_prefix", []) or [])
        if prefix:
            return prefix
        host = self._exporter_host(res)
        if host:
            return sshmanager.get(host).get_prefix() + ["--"]
        return []

    @property
    def _is_remote(self):
        return self._exporter_host(self._remote_resource()) is not None

    def _remote_run(self, cmd, check=False):
        """Run ``cmd`` (argv list) locally or on the exporter, return CompletedProcess."""
        return subprocess.run(self._remote_prefix() + list(cmd), check=check)

    def _remote_check(self, cmd):
        """Run ``cmd`` and raise CalledProcessError on a non-zero exit."""
        return self._remote_run(cmd, check=True)

    def _remote_put(self, local_path: str, remote_path: str) -> None:
        """Copy ``local_path`` to an exact ``remote_path`` on the exporter.

        Uses a reused ssh connection (no per-file ``scp`` handshake). The
        caller is responsible for ensuring the destination directory exists.
        """
        host = self._exporter_host(self._remote_resource())
        if not host:
            raise RuntimeError("_remote_put called on a local resource")
        sshmanager.get(host).put_file(local_path, remote_path)

    def _stage_file(self, local_path: str) -> str:
        """Make ``local_path`` available to the host that will consume it.

        Returns a path valid on that host: the input path unchanged when
        local, or a path on the exporter after copying when remote. Uses
        labgrid's ManagedFile for genuine NetworkResources and a reused ssh
        connection for proxied plain resources.
        """
        res = self._remote_resource()
        host = self._exporter_host(res)
        if not host:
            return local_path
        if isinstance(res, NetworkResource):
            managed = ManagedFile(local_path, res)
            managed.sync_to_resource()
            return managed.get_remote_path()
        # Proxied plain resource: stage via a reused ssh connection into a
        # content-hashed directory (dedupes re-uploads, avoids basename clashes).
        conn = sshmanager.get(host)
        rdir = f"{_STAGE_ROOT}/{_sha256_file(local_path)}"
        conn.run_check(f"mkdir -p {rdir}")
        rpath = f"{rdir}/{os.path.basename(local_path)}"
        conn.put_file(local_path, rpath)
        return rpath
