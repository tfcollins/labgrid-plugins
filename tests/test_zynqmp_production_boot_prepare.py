"""Contract tests for the ZynqMP production BOOT.BIN preparation helper."""

import importlib.util
import os
import struct
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "examples/ultrascale_jtag_boot/prepare-production-boot.py"
SPEC = importlib.util.spec_from_file_location("prepare_production_boot", SCRIPT)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
EXAMPLE_DIR = SCRIPT.parent


def _write_u32(data, offset, value):
    struct.pack_into("<I", data, offset, value)


def _boot_bin(tmp_path, *, encrypted=False):
    data = bytearray(0x3000)
    _write_u32(data, 0x30, 0x2000)
    _write_u32(data, 0x34, 8)
    _write_u32(data, 0x3C, 0x100)
    _write_u32(data, 0x9C, 0x100)

    # PL, BL31, and U-Boot partitions.
    _write_u32(data, 0x100 + 0x04, 2)
    _write_u32(data, 0x100 + 0x0C, 0x140 // 4)
    _write_u32(data, 0x100 + 0x20, 0x1000 // 4)
    _write_u32(data, 0x100 + 0x24, 0x20 | (0x80 if encrypted else 0))
    data[0x1000:0x1008] = bytes.fromhex("665599aa11223344")

    _write_u32(data, 0x140 + 0x04, 2)
    _write_u32(data, 0x140 + 0x0C, 0x180 // 4)
    _write_u32(data, 0x140 + 0x18, 0xFFFEA000)
    _write_u32(data, 0x140 + 0x20, 0x1400 // 4)
    _write_u32(data, 0x140 + 0x24, 0x117)
    data[0x1400:0x1408] = b"BL31_RAW"

    _write_u32(data, 0x180 + 0x04, 2)
    _write_u32(data, 0x180 + 0x18, 0x08000000)
    _write_u32(data, 0x180 + 0x20, 0x1800 // 4)
    _write_u32(data, 0x180 + 0x24, 0x114)
    data[0x1800:0x1808] = b"UBOOTRAW"

    data[0x2000:0x2008] = b"PMUFWRAW"
    data[0x2008:0x2010] = b"FSBL_RAW"
    config = (
        2,
        8,
        1,
        0x101,
        0,
        0x102,
        0,
        0x103,
        0,
        0x104,
        0,
        0x105,
        0,
        0x107,
        0,
        0,
        0x106,
        0,
        0x108,
        0,
        0,
    )
    struct.pack_into(f"<{len(config)}I", data, 0x2020, *config)
    path = tmp_path / "BOOT.BIN"
    path.write_bytes(data)
    return path


def test_extracts_combined_bootloader_and_converts_pl_words(tmp_path):
    output = tmp_path / "out"
    manifest = MODULE.extract(_boot_bin(tmp_path), output)

    assert (output / "pmufw.bin").read_bytes() == b"PMUFWRAW"
    assert (output / "fsbl.bin").read_bytes().startswith(b"FSBL_RAW")
    assert struct.unpack_from("<III", (output / "pm-config-object.bin").read_bytes()) == (2, 8, 1)
    assert (output / "u-boot.bin").read_bytes() == b"UBOOTRAW"
    assert (output / "bl31.bin").read_bytes() == b"BL31_RAW"
    assert (output / "atf-handoff.bin").read_bytes()[:8] == struct.pack("<II", 0x584E4C58, 2)
    assert (output / "system-top-xsdb.bin").read_bytes() == bytes.fromhex("aa99556644332211")
    assert manifest["payloads"]["u-boot.bin"]["bytes"] == 8
    assert (output / "manifest.json").is_file()


def test_rejects_encrypted_partitions(tmp_path):
    with pytest.raises(ValueError, match="encrypted"):
        MODULE.extract(_boot_bin(tmp_path, encrypted=True), tmp_path / "out")


def test_recovery_uboot_recipe_is_pinned_and_complete():
    build = EXAMPLE_DIR / "build-recovery-uboot.sh"
    patch = EXAMPLE_DIR / "recovery-uboot.patch"
    text = build.read_text()
    diff = patch.read_text()
    assert os.access(build, os.X_OK)
    assert "d244ce5869648a5046e98b917ff4d7ca3fd81dfd" in text
    assert "adi_zynqmp_adrv9009_zu11eg_adrv2crr_fmc_defconfig" in text
    assert "apply --check" in text
    assert "arch/arm/cpu/armv8/zynqmp/cpu.c" in diff
    assert "board/xilinx/zynqmp/zynqmp.c" in diff
    assert "drivers/serial/serial_zynq.c" in diff
    assert "0xC2000002" in diff


def test_guardedly_patches_bl31_console_base():
    payload = b"prefix" + struct.pack("<Q", 0xFF000000) * 2 + b"suffix"
    patched, count = MODULE._patch_bl31_console(payload, 0xFF010000)
    assert count == 2
    assert struct.pack("<Q", 0xFF000000) not in patched
    assert patched.count(struct.pack("<Q", 0xFF010000)) == 2
