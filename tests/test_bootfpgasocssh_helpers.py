"""Unit tests for BootFPGASoCSSH static helpers.

These tests exercise the helper without booting hardware so they can run in
the standard `nox -s tests` matrix.
"""

import types

from adi_lg_plugins.strategies.bootfpgasocssh import BootFPGASoCSSH


class _FakeRemoteEntry:
    """Stand-in for labgrid.remote.common.ResourceEntry.

    Mirrors the shape that matters here: a mutable ``data`` dict whose
    ``params`` sub-dict backs the ``args`` property (which returns a copy).
    Mutating ``args`` therefore has no effect — the helper must touch
    ``data['params']`` directly.
    """

    def __init__(self, params):
        self.data = {"cls": "NetworkService", "params": dict(params)}

    @property
    def args(self):
        out = self.data["params"].copy()
        out.pop("extra", None)
        return out


class TestOverrideNetworkserviceAddress:
    """Cover the bug where RemotePlaceManager.poll() reverts the live attr
    back to the coordinator-cached value before SSHDriver.on_activate reads it.
    """

    def test_sets_live_address_when_no_remote_entry(self):
        ns = types.SimpleNamespace(address="10.0.0.23")
        BootFPGASoCSSH._override_networkservice_address(ns, "10.0.0.66")
        assert ns.address == "10.0.0.66"

    def test_updates_remote_entry_backing_store(self):
        # The backing store is data["params"]; args is a property returning
        # a copy, so we must mutate the params dict directly. If we miss
        # this, poll() reads the stale params and reverts the live attr.
        remote_entry = _FakeRemoteEntry({"address": "10.0.0.23", "port": 22})
        ns = types.SimpleNamespace(address="10.0.0.23", _remote_entry=remote_entry)

        BootFPGASoCSSH._override_networkservice_address(ns, "10.0.0.66")

        assert ns.address == "10.0.0.66"
        # Next poll/args read should see the new address.
        assert remote_entry.data["params"]["address"] == "10.0.0.66"
        assert remote_entry.args["address"] == "10.0.0.66"
        # Unrelated keys untouched.
        assert remote_entry.data["params"]["port"] == 22

    def test_remote_entry_without_data_attr_does_not_raise(self):
        remote_entry = types.SimpleNamespace()  # no .data
        ns = types.SimpleNamespace(address="10.0.0.23", _remote_entry=remote_entry)

        BootFPGASoCSSH._override_networkservice_address(ns, "10.0.0.66")

        assert ns.address == "10.0.0.66"

    def test_remote_entry_with_non_dict_data_does_not_raise(self):
        remote_entry = types.SimpleNamespace(data="not a dict")
        ns = types.SimpleNamespace(address="10.0.0.23", _remote_entry=remote_entry)

        BootFPGASoCSSH._override_networkservice_address(ns, "10.0.0.66")

        assert ns.address == "10.0.0.66"
