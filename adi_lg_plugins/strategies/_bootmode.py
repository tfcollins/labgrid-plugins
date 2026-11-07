"""Shared ZynqMP boot-mode override steps for strategies.

A strategy with a ``jtag`` (``XilinxJTAGDriver``) binding can boot a ZynqMP
from a device other than the one its mode switches select, by writing
``CRL_APB.BOOT_MODE_USER`` and system-resetting the board (see
:meth:`XilinxJTAGDriver.set_zynqmp_boot_mode`). The override lasts until the
next power-on reset, so each boot that wants it applies it after power-on.
"""

from __future__ import annotations

from labgrid.strategy import StrategyError

from ..drivers.xilinxjtagdriver import zynqmp_boot_mode_name, zynqmp_boot_mode_value

JTAG = "jtag"


def normalize_boot_mode(mode):
    """Canonical boot mode name for a strategy attribute; ``None``/``""`` = switches."""
    if mode is None or (isinstance(mode, str) and not mode.strip()):
        return None
    return zynqmp_boot_mode_name(zynqmp_boot_mode_value(mode))


def _jtag(strategy):
    jtag = getattr(strategy, "jtag", None)
    if jtag is None:
        raise StrategyError(
            f"{type(strategy).__name__}.boot_mode needs a XilinxJTAGDriver ('jtag' binding)"
        )
    strategy.target.activate(jtag)
    return jtag


def boot_with_override(strategy, mode: str, jtag_url: str) -> dict:
    """Override the boot mode to ``mode`` and system-reset: the board boots from it."""
    jtag = _jtag(strategy)
    info = jtag.set_zynqmp_boot_mode(mode, reset=True, jtag_url=jtag_url)
    strategy.logger.info(
        "Boot mode overridden to %s (switches: %s); system reset issued",
        info["effective_name"],
        info["pins_name"],
    )
    return info


def hold_in_jtag_boot_mode(strategy, jtag_url: str) -> dict:
    """Reset the board into JTAG boot mode, so its BootROM waits for the debugger.

    Stops a board strapped for SD/QSPI/... from booting its own image, e.g.
    before a JTAG bootstrap that would otherwise race it. Verified by reading
    the register back after the reset.
    """
    jtag = _jtag(strategy)
    jtag.set_zynqmp_boot_mode(JTAG, reset=True, jtag_url=jtag_url)
    info = jtag.get_zynqmp_boot_mode(jtag_url=jtag_url)
    if info["effective"] != 0 or not info["use_alt"]:
        raise StrategyError(
            f"board did not stay in JTAG boot mode (BOOT_MODE_USER=0x{info['raw']:08x})"
        )
    strategy.logger.info("Board held in JTAG boot mode (switches: %s)", info["pins_name"])
    return info
