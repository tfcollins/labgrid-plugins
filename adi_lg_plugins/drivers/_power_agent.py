"""Shared AgentWrapper lifecycle for exporter-side power operations."""

from pathlib import Path

from labgrid.resource.common import NetworkResource
from labgrid.util.agentwrapper import AgentWrapper

from ._remote import RemoteExecMixin, _resolvable_host

_AGENT_NAME = "adi_power"
_AGENT_PATH = Path(__file__).with_name("agents")


def create_power_agent(host):
    """Start an AgentWrapper and load the package-owned power helper."""
    wrapper = AgentWrapper(host)
    try:
        module = wrapper.load(_AGENT_NAME, path=str(_AGENT_PATH))
    except Exception:
        wrapper.close()
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
