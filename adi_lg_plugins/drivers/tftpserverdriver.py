"""TFTP server driver whose service runs on the bound resource's exporter."""

import base64
import os
from types import SimpleNamespace

import attr
from labgrid.driver.common import Driver
from labgrid.factory import target_factory
from labgrid.util.agentwrapper import AgentWrapper

from adi_lg_plugins.artifacts import ArtifactRef
from adi_lg_plugins.resources.tftpserver import TFTPServerResource

from ._remote import RemoteExecMixin

_AGENT_PATH = os.path.join(os.path.dirname(__file__), "agents")
_UPLOAD_CHUNK_SIZE = 64 * 1024


@target_factory.reg_driver
@attr.s(eq=False)
class TFTPServerDriver(RemoteExecMixin, Driver):
    """Run and populate a read-only TFTP server on the resource exporter.

    Local resources use the same AgentWrapper service with ``host=None``. For a
    resource reconstructed through a ``RemotePlace``, the exporter host is read
    from ``resource.extra['proxy']`` and the agent, UDP socket, root directory,
    and uploads all live on that exporter.
    """

    bindings = {"resource": TFTPServerResource}
    _remote_binding = "resource"

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self.wrapper = None
        self.proxy = None
        # Kept as metadata for callers which historically inspected
        # ``driver.server.address/port/root``.
        self.server = None

    def on_activate(self):
        if self.wrapper is not None:
            return
        wrapper = AgentWrapper(self._exporter_host(self.resource))
        try:
            proxy = wrapper.load("tftp", path=_AGENT_PATH)
            info = proxy.start(self.resource.address, self.resource.port, self.resource.root)
        except Exception:
            wrapper.close()
            raise
        self.wrapper = wrapper
        self.proxy = proxy
        self.server = SimpleNamespace(**info)

    def on_deactivate(self):
        wrapper = self.wrapper
        proxy = self.proxy
        self.wrapper = None
        self.proxy = None
        self.server = None
        if wrapper is None:
            return
        try:
            if proxy is not None:
                proxy.stop()
        finally:
            wrapper.close()

    def _require_server(self):
        if self.proxy is None or self.server is None:
            raise RuntimeError("TFTPServerDriver is not active")

    def _server_address(self):
        self._require_server()
        return f"{self.server.address}:{self.server.port}"

    @Driver.check_active
    def get_server_address(self):
        """Return the DUT-visible ``address:port`` advertised by the exporter."""
        return self._server_address()

    @Driver.check_active
    def get_server_ip(self):
        """Return the DUT-visible IPv4 address advertised by the exporter."""
        self._require_server()
        return self.server.address

    @Driver.check_active
    def get_server_port(self):
        """Return the UDP port bound by the exporter-side server."""
        self._require_server()
        return self.server.port

    def publish(self, client_path, destination=None):
        """Atomically publish a client file into the exporter-side TFTP root.

        Args:
            client_path: Path readable by the labgrid client.
            destination: Relative POSIX filename visible to the DUT. Defaults to
                the source basename. Dot components are normalized by the
                exporter; absolute paths, backslashes, and traversal are rejected.

        Returns:
            A mapping with normalized ``filename`` and DUT-visible ``address``.
        """
        self._require_server()
        client_path = os.fspath(client_path)
        if not os.path.isfile(client_path):
            raise FileNotFoundError(client_path)
        if destination is None:
            destination = os.path.basename(client_path)
        if not isinstance(destination, str):
            destination = os.fspath(destination)

        token = self.proxy.begin_upload(destination)
        try:
            with open(client_path, "rb") as source:
                for chunk in iter(lambda: source.read(_UPLOAD_CHUNK_SIZE), b""):
                    encoded = base64.b85encode(chunk).decode("ascii")
                    self.proxy.write_upload(token, encoded)
            filename = self.proxy.finish_upload(token)
        except Exception:
            self.proxy.abort_upload(token)
            raise
        return {"filename": filename, "address": self._server_address()}

    def stage_file(self, client_path, destination=None):
        """Backward-friendly alias for :meth:`publish`."""
        return self.publish(client_path, destination)

    def publish_artifact(self, artifact: ArtifactRef, destination=None):
        """Publish an artifact, retaining it on the exporter when co-located."""
        self._require_server()
        destination = destination or os.path.basename(artifact.path)
        host = self._exporter_host(self.resource)
        if artifact.host == host:
            filename = self.proxy.publish_existing(artifact.path, destination, artifact.sha256)
            return {"filename": filename, "address": self._server_address()}
        local_path = artifact.path
        if artifact.host is not None:
            cache = os.path.join(
                os.path.expanduser("~/.cache/labgrid/artifacts"),
                artifact.sha256,
                os.path.basename(artifact.path),
            )
            local_path = artifact.materialize_on_client(cache)
        return self.publish(local_path, destination)
