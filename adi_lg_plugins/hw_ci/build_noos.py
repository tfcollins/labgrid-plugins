"""Build a no-os reference project for hardware CI: compose the Vivado/Vitis
environment (proven on the lab runners), fetch the board's ``.xsa`` from Kuiper,
and orchestrate ``make`` — collapsing the DUT's inline build shell into one
unit-tested entry point.

The lab/toolchain knowledge that used to live in no-os's ``build-cmd`` lives
here: Vivado auto-detect + sourcing under ``set +u`` (2025.1 unbound-PYTHONPATH
quirk), the libtinfo ``.so.5``->``.so.6`` shim (Vitis on Ubuntu 24.04), the
``NOOS_VITIS_HSI_FLOW`` flag (pure-hsi flow, no Eclipse backend), and the
``.xsa`` -> ``system_top.bit`` / ``ps7_init.tcl`` extraction the JTAG flash needs.
"""

from __future__ import annotations

import glob
import logging
import os
import subprocess
import zipfile
from pathlib import Path

from .kuiper_xsa import fetch_board_xsa

logger = logging.getLogger(__name__)

_VIVADO_GLOBS = (
    "/opt/Xilinx/Vivado/*/settings64.sh",
    "/tools/Xilinx/*/Vivado/settings64.sh",
)
_SHIM_STEMS = ("libtinfo", "libncurses", "libncursesw")
_SO6_SEARCH = (
    "/usr/lib/x86_64-linux-gnu",
    "/usr/lib",
    "/lib/x86_64-linux-gnu",
    "/usr/lib64",
)


def detect_vivado_settings() -> Path:
    """Return the Vivado ``settings64.sh`` to source: ``$VITIS_SETTINGS`` if set,
    else the newest match under the known install roots."""
    explicit = os.environ.get("VITIS_SETTINGS")
    if explicit:
        return Path(explicit)
    found: list[str] = []
    for pat in _VIVADO_GLOBS:
        found.extend(glob.glob(pat))
    if not found:
        raise FileNotFoundError(
            f"no Vivado settings64.sh found under {_VIVADO_GLOBS}; set VITIS_SETTINGS to the path"
        )
    return Path(sorted(found)[-1])


def source_env(settings: Path) -> dict[str, str]:
    """Source ``settings`` in a subshell (tolerating unbound vars under set -u)
    and capture the resulting environment as a dict."""
    out = subprocess.check_output(
        ["bash", "-c", f'set +u; source "{settings}" >/dev/null 2>&1; env -0'],
        text=True,
    )
    env: dict[str, str] = {}
    for chunk in out.split("\0"):
        if not chunk:
            continue
        key, _, value = chunk.partition("=")
        env[key] = value
    return env


def _find_so6(stem: str) -> Path | None:
    for d in _SO6_SEARCH:
        cand = Path(d) / f"{stem}.so.6"
        if cand.exists():
            return cand
    return None


def ensure_libtinfo_shim(shim_dir: str | None = None) -> Path:
    """Ensure ``<shim_dir>/{libtinfo,libncurses,libncursesw}.so.5`` exist as
    symlinks to the system ``.so.6`` (idempotent). Returns the shim dir."""
    shim = Path(shim_dir or Path.home() / ".local" / "xlnxshim")
    shim.mkdir(parents=True, exist_ok=True)
    for stem in _SHIM_STEMS:
        link = shim / f"{stem}.so.5"
        if link.exists() or link.is_symlink():
            continue
        target = _find_so6(stem)
        if target is None:
            raise FileNotFoundError(
                f"cannot find {stem}.so.6 on host (install lib{stem}6) to build the shim"
            )
        link.symlink_to(target)
    return shim


def compose_build_env(settings: Path) -> dict[str, str]:
    """Full environment for the no-os make: base env + Vivado env + the libtinfo
    shim on LD_LIBRARY_PATH + the pure-hsi flow flag."""
    env = dict(os.environ)
    env.update(source_env(settings))
    shim = ensure_libtinfo_shim()
    env["LD_LIBRARY_PATH"] = os.pathsep.join([str(shim), env.get("LD_LIBRARY_PATH", "")]).rstrip(
        os.pathsep
    )
    env["NOOS_VITIS_HSI_FLOW"] = "1"
    return env


def build_noos(
    *,
    project: str,
    carrier: str,
    board: str,
    release: str,
    build_vars: dict[str, str] | None = None,
    noos_root: str = ".",
    xsa_dir: str | None = None,
) -> dict[str, str]:
    """Build ``projects/<project>`` and return artifact paths.

    Fetches the board's ``.xsa`` from the Kuiper ``release``, copies it into the
    project, extracts ``system_top.bit`` + ``ps7_init.tcl`` into ``build_hw/``
    (the JTAG flash inputs), and runs ``make`` with the composed env + build
    vars. Returns ``{"elf", "bitstream", "ps7_init"}`` host paths."""
    root = Path(noos_root)
    proj_dir = root / "projects" / project
    if not proj_dir.is_dir():
        raise FileNotFoundError(f"no-os project dir not found: {proj_dir}")

    settings = detect_vivado_settings()
    env = compose_build_env(settings)

    xsa = fetch_board_xsa(release, board, carrier, xsa_dir=xsa_dir)
    proj_xsa = proj_dir / "system_top.xsa"
    proj_xsa.write_bytes(Path(xsa).read_bytes())

    build_hw = proj_dir / "build_hw"
    build_hw.mkdir(exist_ok=True)
    with zipfile.ZipFile(xsa) as z:
        for name in ("ps7_init.tcl", "system_top.bit"):
            member = next((n for n in z.namelist() if Path(n).name == name), None)
            if member is None:
                raise FileNotFoundError(f"{name} not found inside {xsa}")
            (build_hw / name).write_bytes(z.read(member))

    cmd = ["make", "-C", str(proj_dir)]
    for key, value in (build_vars or {}).items():
        cmd.append(f"{key}={value}")
    logger.info("building no-os project %s: %s", project, " ".join(cmd))
    result = subprocess.run(cmd, env=env, cwd=str(root))
    if result.returncode != 0:
        raise RuntimeError(f"make failed for projects/{project} (exit {result.returncode})")

    arts = {
        "elf": str(proj_dir / "build" / f"{project}.elf"),
        "bitstream": str(build_hw / "system_top.bit"),
        "ps7_init": str(build_hw / "ps7_init.tcl"),
    }
    for label, path in arts.items():
        print(f"{label}={path}")
    return arts
