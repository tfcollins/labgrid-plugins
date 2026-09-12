"""Exporter-side execution tests for network/API power drivers."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from labgrid import Target
from labgrid.binding import BindingState

from adi_lg_plugins.drivers.apcpowerdriver import APCDriver
from adi_lg_plugins.drivers.cyberpowerdriver import CyberPowerDriver
from adi_lg_plugins.drivers.homeassistantdriver import HomeAssistantPowerDriver
from adi_lg_plugins.drivers.kasadriver import KasaPowerDriver
from adi_lg_plugins.drivers.vesyncdriver import VesyncPowerDriver
from adi_lg_plugins.resources.apcpdu import APCOutlet
from adi_lg_plugins.resources.cyberpowerpdu import CyberPowerOutlet
from adi_lg_plugins.resources.homeassistant import HomeAssistantOutlet
from adi_lg_plugins.resources.kasa import KasaOutlet
from adi_lg_plugins.resources.vesync import VesyncOutlet


def _remote_driver(driver_type, binding, resource):
    driver = driver_type.__new__(driver_type)
    setattr(driver, binding, resource)
    driver.logger = MagicMock()
    driver.state = BindingState.active
    driver._init_exporter_agent()
    driver._agent_module = MagicMock()
    if hasattr(resource, "outlet"):
        driver.outlet = resource.outlet
    return driver


def test_apc_remote_operations_use_exporter_agent():
    resource = SimpleNamespace(
        extra={"proxy": "exporter.example.com"},
        address="10.0.0.10",
        outlet=3,
        read_community="reader",
        write_community="writer",
        delay=0.0,
    )
    driver = _remote_driver(APCDriver, "APC_outlet", resource)
    driver._agent_module.apc_get.return_value = 1

    driver.on()
    driver.off()
    assert driver.get() is True

    driver._agent_module.apc_set.assert_any_call("10.0.0.10", 3, True)
    driver._agent_module.apc_set.assert_any_call("10.0.0.10", 3, False)
    driver._agent_module.apc_get.assert_called_once_with("10.0.0.10", 3)


def test_cyberpower_remote_operations_use_exporter_agent():
    resource = SimpleNamespace(
        extra={"proxy": "exporter.example.com"}, address="10.0.0.11", outlet=4, delay=0.0
    )
    driver = _remote_driver(CyberPowerDriver, "cyberpower_outlet", resource)

    driver.on()
    driver.off()

    driver._agent_module.cyberpower_set.assert_any_call("10.0.0.11", 4, True)
    driver._agent_module.cyberpower_set.assert_any_call("10.0.0.11", 4, False)


def test_homeassistant_remote_operations_use_exporter_agent():
    resource = SimpleNamespace(
        extra={"proxy": "exporter.example.com"},
        url="http://ha.local:8123",
        token="token",
        entity_id="switch.bench",
        delay=0.0,
    )
    driver = _remote_driver(HomeAssistantPowerDriver, "ha_outlet", resource)
    driver._agent_module.homeassistant.return_value = True

    driver.on()
    driver.off()
    assert driver.get() is True

    driver._agent_module.homeassistant.assert_any_call("on", "http://ha.local:8123", "switch.bench")
    driver._agent_module.homeassistant.assert_any_call(
        "off", "http://ha.local:8123", "switch.bench"
    )
    driver._agent_module.homeassistant.assert_any_call(
        "get", "http://ha.local:8123", "switch.bench"
    )


def test_kasa_remote_operations_use_exporter_agent():
    resource = SimpleNamespace(
        extra={"proxy": "exporter.example.com"},
        host="10.0.0.12",
        outlets="left,right",
        username="user@example.com",
        password="secret",
        delay=0.0,
    )
    driver = _remote_driver(KasaPowerDriver, "kasa_outlet", resource)
    driver._agent_module.kasa.return_value = True

    driver.on()
    driver.off()
    assert driver.get() is True

    common = ("10.0.0.12", "left,right")
    driver._agent_module.kasa.assert_any_call("on", *common)
    driver._agent_module.kasa.assert_any_call("off", *common)
    driver._agent_module.kasa.assert_any_call("get", *common)


def test_vesync_remote_operations_use_exporter_agent():
    resource = SimpleNamespace(
        extra={"proxy": "exporter.example.com"},
        outlet_names="bench, dut",
        username="user@example.com",
        password="secret",
        delay=0.0,
    )
    driver = _remote_driver(VesyncPowerDriver, "vesync_outlet", resource)
    driver._agent_module.vesync.return_value = True

    driver.on()
    driver.off()
    assert driver.get() is True

    common = ("bench, dut",)
    driver._agent_module.vesync.assert_any_call("on", *common)
    driver._agent_module.vesync.assert_any_call("off", *common)
    driver._agent_module.vesync.assert_any_call("get", *common)


@pytest.mark.parametrize(
    ("driver_type", "binding"),
    [
        (APCDriver, "APC_outlet"),
        (CyberPowerDriver, "cyberpower_outlet"),
        (HomeAssistantPowerDriver, "ha_outlet"),
        (KasaPowerDriver, "kasa_outlet"),
        (VesyncPowerDriver, "vesync_outlet"),
    ],
)
def test_remote_driver_activation_loads_agent_and_deactivation_closes(driver_type, binding):
    driver = driver_type.__new__(driver_type)
    setattr(driver, binding, SimpleNamespace(extra={"proxy": "exporter.example.com"}))
    driver._init_exporter_agent()
    wrapper = MagicMock()
    module = MagicMock()
    wrapper.load.return_value = module

    with patch(
        "adi_lg_plugins.drivers._power_agent.AgentWrapper", return_value=wrapper
    ) as wrapper_type:
        driver.on_activate()
        wrapper_type.assert_called_once_with("exporter.example.com")
        assert driver._agent_module is module
        driver.on_deactivate()

    wrapper.close.assert_called_once_with()
    assert driver._agent_wrapper is None
    assert driver._agent_module is None


def test_uploaded_helper_executes_through_real_agentwrapper():
    """Exercise labgrid's source upload/registration path, not a mocked proxy."""
    from adi_lg_plugins.drivers._power_agent import create_power_agent

    wrapper, module = create_power_agent(None)
    try:
        assert module.probe() == ["apc", "cyberpower", "homeassistant", "kasa", "vesync"]
        assert {
            "adi_power.apc_get",
            "adi_power.apc_set",
            "adi_power.cyberpower_set",
            "adi_power.homeassistant",
            "adi_power.kasa",
            "adi_power.vesync",
        } <= set(wrapper.list())
    finally:
        wrapper.close()


def test_proxy_required_fails_before_agent_creation():
    driver = APCDriver.__new__(APCDriver)
    driver.APC_outlet = SimpleNamespace(
        extra={"proxy": "isolated.example.com", "proxy_required": True}
    )
    driver._init_exporter_agent()
    with (
        patch("adi_lg_plugins.drivers._power_agent.AgentWrapper") as wrapper_type,
        pytest.raises(RuntimeError, match="ProxyJump"),
    ):
        driver.on_activate()
    wrapper_type.assert_not_called()


@pytest.mark.parametrize(
    ("driver_type", "resource_type", "resource_kwargs", "client_path"),
    [
        (
            APCDriver,
            APCOutlet,
            {"address": "10.0.0.10", "outlet": 1},
            "adi_lg_plugins.drivers.apcpowerdriver.APCPdu",
        ),
        (
            CyberPowerDriver,
            CyberPowerOutlet,
            {"address": "10.0.0.11", "outlet": 2},
            "adi_lg_plugins.drivers.cyberpowerdriver.CyberPowerPdu",
        ),
        (
            HomeAssistantPowerDriver,
            HomeAssistantOutlet,
            {"url": "http://ha.local:8123", "token": "token", "entity_id": "switch.bench"},
            "adi_lg_plugins.drivers.homeassistantdriver.HomeAssistantClient",
        ),
        (
            KasaPowerDriver,
            KasaOutlet,
            {"host": "10.0.0.12"},
            "adi_lg_plugins.drivers.kasadriver.Discover.discover_single",
        ),
        (
            VesyncPowerDriver,
            VesyncOutlet,
            {"outlet_names": "bench", "username": "user@example.com", "password": "secret"},
            "adi_lg_plugins.drivers.vesyncdriver.VeSync",
        ),
    ],
)
def test_remote_post_init_defers_clients_and_target_lifecycle_closes_agent(
    driver_type, resource_type, resource_kwargs, client_path
):
    target = Target(f"remote-{driver_type.__name__}")
    resource = resource_type(target, None, **resource_kwargs)
    resource.extra = {"proxy": "exporter.example.com"}
    wrapper = MagicMock()
    wrapper.load.return_value = MagicMock()

    with (
        patch(client_path) as client,
        patch("adi_lg_plugins.drivers._power_agent.AgentWrapper", return_value=wrapper),
    ):
        driver = driver_type(target, None)
        client.assert_not_called()
        target.activate(driver)
        target.deactivate(driver)

    wrapper.close.assert_called_once_with()
