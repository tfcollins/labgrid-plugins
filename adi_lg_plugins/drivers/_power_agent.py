"""Shared AgentWrapper lifecycle for exporter-side power operations."""

import logging
import socket
import subprocess
from pathlib import Path

from labgrid.resource.common import NetworkResource
from labgrid.util.agentwrapper import AgentWrapper

from ._remote import RemoteExecMixin, _resolvable_host

_AGENT_NAME = "adi_power"
_AGENT_PATH = Path(__file__).with_name("agents")


def create_power_agent(host):
    """Start an AgentWrapper and load the package-owned power helper."""
    if host and host.rstrip(".").casefold() in {
        socket.gethostname().rstrip(".").casefold(),
        socket.getfqdn().rstrip(".").casefold(),
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        # A coordinator resource is still marked remote when the client runs
        # on its exporter. Use this interpreter instead of requiring self-SSH.
        host = None
    logging.getLogger(__name__).info("Starting %s power agent", "SSH" if host else "local")
    wrapper = AgentWrapper(host)
    try:
        module = wrapper.load(_AGENT_NAME, path=str(_AGENT_PATH))
    except BaseException:
        # A stalled agent cannot acknowledge close(). Stop its process before
        # closing the wrapper so stage timeouts and cancellation stay bounded.
        process = getattr(wrapper, "agent", None)
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            wrapper.agent = None
        try:
            wrapper.close()
        except (OSError, ValueError):
            pass  # Preserve the load/timeout exception if the pipe is already gone.
        raise
    return wrapper, module


class ExporterPowerAgentMixin(RemoteExecMixin):
    """Route power API work to the exporter for proxied custom resources."""

    def _init_exporter_agent(self):
        self._agent_wrapper = None
        self._agent_module = None

    def _power_exporter_host(self):
        """Return only the exporter host, never a device/API endpoint host."""
        try:
            resource = self._remote_resource()
        except AttributeError:
            # Keep direct unit-style instances usable when no binding was set.
            return None
        if isinstance(resource, NetworkResource):
            return self._exporter_host(resource)
        extra = getattr(resource, "extra", None) or {}
        proxy = extra.get("proxy") if isinstance(extra, dict) else None
        return _resolvable_host(proxy) if proxy else None

    @property
    def _is_remote(self):
        return self._power_exporter_host() is not None

    def on_activate(self):
        host = self._power_exporter_host()
        if host is not None:
            resource = self._remote_resource()
            extra = getattr(resource, "extra", None) or {}
            if isinstance(extra, dict) and extra.get("proxy_required"):
                raise RuntimeError(
                    "exporter requires a proxy, but labgrid AgentWrapper needs direct SSH; "
                    "configure an SSH ProxyJump for the exporter host"
                )
            self._agent_wrapper, self._agent_module = create_power_agent(host)

    def on_deactivate(self):
        wrapper = self._agent_wrapper
        self._agent_wrapper = None
        self._agent_module = None
        if wrapper is not None:
            wrapper.close()

    def _exporter_call(self, method, *args):
        if self._agent_module is None:
            raise RuntimeError("exporter power agent is not active")
        return getattr(self._agent_module, method)(*args)
