"""AgentWrapper source for allowlisted power operations.

This file is uploaded and executed as a standalone module by labgrid's agent.
It must not use relative imports or depend on state in the controlling process.
"""

import asyncio
import os


def _secret(name, required=True):
    value = os.environ.get(name)
    if value:
        return value
    path = os.path.expanduser(
        os.environ.get("ADI_LG_CREDENTIAL_FILE", "~/.config/adi-lg/credentials.env")
    )
    try:
        if os.stat(path).st_mode & 0o077:
            raise RuntimeError(f"exporter credential file {path} must have mode 0600")
        with open(path) as stream:
            for line in stream:
                key, separator, candidate = line.rstrip("\n").partition("=")
                if separator and key == name:
                    value = candidate
                    break
    except FileNotFoundError:
        pass
    if not value:
        if not required:
            return None
        raise RuntimeError(
            f"exporter credential {name} is required in the environment or credential file"
        )
    return value


def handle_probe():
    """Return the fixed set of supported backends for upload smoke tests."""
    return ["apc", "cyberpower", "homeassistant", "kasa", "vesync"]


def handle_apc_set(address, outlet, on):
    from adi_lg_plugins.drivers.apcpowerdriver import APCPdu

    APCPdu(
        address,
        _secret("ADI_LG_APC_READ_COMMUNITY"),
        _secret("ADI_LG_APC_WRITE_COMMUNITY"),
    ).set_outlet_on(outlet, on)


def handle_apc_get(address, outlet):
    from adi_lg_plugins.drivers.apcpowerdriver import APCPdu

    return APCPdu(
        address,
        _secret("ADI_LG_APC_READ_COMMUNITY"),
        _secret("ADI_LG_APC_WRITE_COMMUNITY"),
    ).get_outlet_status(outlet)


def handle_cyberpower_set(address, outlet, on):
    from adi_lg_plugins.drivers.cyberpowerdriver import CyberPowerPdu

    CyberPowerPdu(address).set_outlet_on(outlet, on)


def handle_homeassistant(action, url, entity_id):
    from adi_lg_plugins.drivers.homeassistantdriver import HomeAssistantClient

    client = HomeAssistantClient(url, _secret("ADI_LG_HOMEASSISTANT_TOKEN"))
    if action == "on":
        client.turn_on(entity_id)
        return None
    if action == "off":
        client.turn_off(entity_id)
        return None
    if action == "get":
        return client.get_state(entity_id)
    raise ValueError(f"unsupported Home Assistant action: {action!r}")


async def _kasa_operation(action, host, selector, username, password):
    from kasa import Discover

    kwargs = {}
    if username and password:
        kwargs["username"] = username
        kwargs["password"] = password
    device = await Discover.discover_single(host, **kwargs)
    if device is None:
        raise RuntimeError(f"No Kasa device found at {host!r}")
    await device.update()
    try:
        children = list(device.children)
        if selector:
            targets = []
            for token in selector.split(","):
                token = token.strip()
                if not token:
                    continue
                if token.lstrip("-").isdigit():
                    index = int(token)
                    if index < 0 or index >= len(children):
                        raise ValueError(
                            f"Kasa outlet index {index} out of range "
                            f"(device has {len(children)} children)"
                        )
                    targets.append(children[index])
                    continue
                target = next((child for child in children if child.alias == token), None)
                if target is None:
                    known = [child.alias for child in children]
                    raise ValueError(f"Kasa outlet {token!r} not found (known outlets: {known})")
                targets.append(target)
        else:
            targets = children if children else [device]

        if action == "get":
            return all(target.is_on for target in targets)
        if action not in {"on", "off"}:
            raise ValueError(f"unsupported Kasa action: {action!r}")
        method = "turn_on" if action == "on" else "turn_off"
        for target in targets:
            await getattr(target, method)()
        return None
    finally:
        await device.disconnect()


def handle_kasa(action, host, selector):
    return asyncio.run(
        _kasa_operation(
            action,
            host,
            selector,
            _secret("ADI_LG_KASA_USERNAME", required=False),
            _secret("ADI_LG_KASA_PASSWORD", required=False),
        )
    )


def handle_vesync(action, outlet_names):
    from pyvesync import VeSync

    manager = VeSync(
        _secret("ADI_LG_VESYNC_USERNAME"),
        _secret("ADI_LG_VESYNC_PASSWORD"),
    )
    manager.login()
    if not manager.enabled:
        raise RuntimeError("Failed to login to VeSync account")
    manager.get_devices()
    manager.update()
    if not manager.outlets:
        raise RuntimeError("No VeSync outlets found for this account")

    known = [outlet.device_name for outlet in manager.outlets]
    requested = [name.strip() for name in outlet_names.split(",") if name.strip()]
    if not requested:
        raise ValueError("No outlet names provided")
    outlets = []
    for name in requested:
        outlet = next((item for item in manager.outlets if item.device_name == name), None)
        if outlet is None:
            raise ValueError(f"Outlet {name} not found (known outlets: {known})")
        outlets.append(outlet)

    if action == "get":
        return all(outlet.is_on for outlet in outlets)
    if action not in {"on", "off"}:
        raise ValueError(f"unsupported VeSync action: {action!r}")
    method = "turn_on" if action == "on" else "turn_off"
    for outlet in outlets:
        getattr(outlet, method)()
    return None


methods = {
    "probe": handle_probe,
    "apc_set": handle_apc_set,
    "apc_get": handle_apc_get,
    "cyberpower_set": handle_cyberpower_set,
    "homeassistant": handle_homeassistant,
    "kasa": handle_kasa,
    "vesync": handle_vesync,
}
