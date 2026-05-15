"""Unit tests for BootFPGASoCSSH static helpers.

These tests exercise the helper without booting hardware so they can run in
the standard `nox -s tests` matrix.
"""

import types

from adi_lg_plugins.strategies.bootfpgasocssh import BootFPGASoCSSH


class TestOverrideNetworkserviceAddress:
    """Cover the bug where RemotePlaceManager.poll() reverts the live attr
    back to the coordinator-cached value before SSHDriver.on_activate reads it.

    See labgrid/resource/remote.py:RemotePlaceManager.poll — it iterates
    ``resource._remote_entry.args`` and setattr's every key back onto the
    live resource every ~timeout seconds.
    """

    def test_sets_live_address_when_no_remote_entry(self):
        ns = types.SimpleNamespace(address="10.0.0.23")
        BootFPGASoCSSH._override_networkservice_address(ns, "10.0.0.66")
        assert ns.address == "10.0.0.66"

    def test_updates_both_live_attr_and_remote_entry_args(self):
        remote_entry = types.SimpleNamespace(args={"address": "10.0.0.23", "port": 22})
        ns = types.SimpleNamespace(address="10.0.0.23", _remote_entry=remote_entry)

        BootFPGASoCSSH._override_networkservice_address(ns, "10.0.0.66")

        assert ns.address == "10.0.0.66"
        # The poll loop reads this back over the live attr; if we miss this,
        # the live attr gets reverted to the stale coordinator value.
        assert remote_entry.args["address"] == "10.0.0.66"
        # Unrelated keys must be untouched.
        assert remote_entry.args["port"] == 22

    def test_remote_entry_without_args_attr_does_not_raise(self):
        remote_entry = types.SimpleNamespace()  # no .args
        ns = types.SimpleNamespace(address="10.0.0.23", _remote_entry=remote_entry)

        BootFPGASoCSSH._override_networkservice_address(ns, "10.0.0.66")

        assert ns.address == "10.0.0.66"
