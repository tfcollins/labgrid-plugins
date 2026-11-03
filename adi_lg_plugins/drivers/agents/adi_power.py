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
    return ["apc", "cyberpower", "homeassistant", "kasa", "scpi", "vesync"]


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
    """Operate Home Assistant without importing the labgrid driver package.

    AgentWrapper starts this helper with the exporter's system ``python3``.
    That interpreter intentionally need not have labgrid installed, while the
    full ``HomeAssistantClient`` driver imports labgrid at module load time.
    Keep this allowlisted operation self-contained instead.
    """
    import requests

    url = url.rstrip("/")
    token = _secret("ADI_LG_HOMEASSISTANT_TOKEN")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    domain = entity_id.split(".", 1)[0]
    if action in {"on", "off"}:
        response = requests.post(
            f"{url}/api/services/{domain}/turn_{action}",
            headers=headers,
            json={"entity_id": entity_id},
            timeout=10,
        )
        response.raise_for_status()
        return None
    if action == "get":
        response = requests.get(f"{url}/api/states/{entity_id}", headers=headers, timeout=10)
        response.raise_for_status()
        return response.json().get("state") == "on"
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


def handle_scpi(action, host, port, channels):
    """Switch or read SCPI bench-supply outputs; self-contained like the other helpers."""
    import re
    import socket

    channels = channels.replace(" ", "")
    if not re.match(r"^\d+(,\d+)*$", channels):
        raise ValueError(f"SCPI channels must be digits separated by commas, got {channels!r}")
    if action not in {"on", "off", "get"}:
        raise ValueError(f"unsupported SCPI action: {action!r}")
    with socket.create_connection((host, port), timeout=5.0) as sock:
        stream = sock.makefile("rw", newline="\n")
        if action == "get":
            states = []
            for channel in channels.split(","):
                stream.write(f"OUTP? (@{channel})\n")
                stream.flush()
                states.append(stream.readline().strip() in {"1", "ON"})
            return all(states)
        stream.write(f"OUTP {action.upper()},(@{channels})\n")
        stream.write("SYST:ERR?\n")
        stream.flush()
        error = stream.readline().strip()
        if not error.startswith("+0") and not error.startswith("0"):
            raise RuntimeError(f"SCPI supply at {host} rejected OUTP {action}: {error}")
    return None


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
    "scpi": handle_scpi,
    "vesync": handle_vesync,
}
