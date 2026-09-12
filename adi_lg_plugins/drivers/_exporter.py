"""Shared labgrid-agent execution for custom resources on exporters.

labgrid exports custom resources as plain ``Resource`` instances.  Their
exporter identity is carried in ``extra['proxy']``; this mixin uses labgrid's
native :class:`AgentWrapper` to execute a narrow package helper on that host.
"""

from pathlib import Path

from labgrid.util.agentwrapper import AgentWrapper

from ._remote import RemoteExecMixin

_AGENT_PATH = str(Path(__file__).resolve().parent.parent / "agents")


class ExporterAgentMixin:
    """Lifecycle and dispatch for an allowlisted labgrid agent helper."""

    _exporter_binding: str = ""
    _exporter_agent: str = ""

    def _exporter_resource(self):
        if not self._exporter_binding:
            raise AttributeError(f"{type(self).__name__} must set _exporter_binding")
        return getattr(self, self._exporter_binding)

    @property
    def _exporter_host(self):
        return RemoteExecMixin._exporter_host(self._exporter_resource())

    @property
    def _runs_on_exporter(self):
        return self._exporter_host is not None

    def _exporter_agent_init(self):
        self._agent_wrapper = None
        self._agent_proxy = None

    def _exporter_agent_activate(self):
        if not self._runs_on_exporter:
            return
        extra = getattr(self._exporter_resource(), "extra", None) or {}
        if isinstance(extra, dict) and extra.get("proxy_required"):
            raise RuntimeError(
                "exporter requires a proxy, but labgrid AgentWrapper needs direct SSH; "
                "configure an SSH ProxyJump for the exporter host"
            )
        if not self._exporter_agent:
            raise AttributeError(f"{type(self).__name__} must set _exporter_agent")
        self._agent_wrapper = AgentWrapper(self._exporter_host)
        try:
            self._agent_proxy = self._agent_wrapper.load(self._exporter_agent, _AGENT_PATH)
        except Exception:
            self._agent_wrapper.close()
            self._agent_wrapper = None
            raise

    def _exporter_agent_deactivate(self):
        if self._agent_wrapper is not None:
            self._agent_wrapper.close()
        self._agent_wrapper = None
        self._agent_proxy = None

    def _exporter_call(self, method, *args, **kwargs):
        if self._agent_proxy is None:
            raise RuntimeError(f"{type(self).__name__} exporter agent is not active")
        return getattr(self._agent_proxy, method)(*args, **kwargs)
