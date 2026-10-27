"""KasaPowerDriver must register without python-kasa installed.

python-kasa is an optional extra and is only needed where Kasa I/O actually
runs: on the client for a local KasaOutlet, or on the exporter (via the power
agent) for a RemotePlace. Each test runs in a fresh interpreter with ``kasa``
blocked, because the import-time behaviour is what is under test.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

_BLOCK_KASA = "import sys; sys.modules['kasa'] = None  # any `import kasa` raises ImportError\n"


def _run(body: str) -> subprocess.CompletedProcess:
    code = _BLOCK_KASA + textwrap.dedent(body)
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)


def test_driver_registers_without_kasa_and_logs_no_warning():
    result = _run(
        """
        import logging
        logging.basicConfig(level=logging.WARNING)
        import adi_lg_plugins
        from labgrid.factory import target_factory
        assert "KasaPowerDriver" in target_factory.drivers
        """
    )

    assert result.returncode == 0, result.stderr
    assert "kasadriver" not in result.stderr


def test_local_power_call_without_kasa_explains_the_extra():
    result = _run(
        """
        from unittest.mock import MagicMock
        from labgrid.binding import BindingState
        from adi_lg_plugins.drivers.kasadriver import KasaPowerDriver
        from adi_lg_plugins.resources.kasa import KasaOutlet

        # Same construction as tests/test_kasa.py::_driver - a local (non-proxied)
        # KasaOutlet, so on() takes the client-side python-kasa path.
        drv = KasaPowerDriver.__new__(KasaPowerDriver)
        drv.kasa_outlet = MagicMock(spec=KasaOutlet, host="10.0.0.5", outlets=None,
                                    username=None, password=None, delay=0.0)
        drv.logger = MagicMock()
        drv.state = BindingState.active
        try:
            drv.on()
        except RuntimeError as e:
            print(e)
        """
    )

    assert result.returncode == 0, result.stderr
    assert "python-kasa" in result.stdout
    assert "[kasa]" in result.stdout
