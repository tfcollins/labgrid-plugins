#!/usr/bin/env python3
"""Extract raw production-handoff payloads from an unencrypted ZynqMP BOOT.BIN."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

BOOT_SOURCE_OFFSET = 0x30
PMUFW_LENGTH_OFFSET = 0x34
FSBL_LENGTH_OFFSET = 0x3C
PHT_OFFSET = 0x9C
PHT_SIZE = 0x40
DEST_DEVICE_MASK = 0x70
DEST_DEVICE_PL = 0x20
ENCRYPTION_MASK = 0x80
BL31_ADDRESS = 0xFFFEA000
ATF_HANDOFF_MAGIC = 0x584E4C58
ATF_HANDOFF_MAX_ENTRIES = 8
DEFAULT_BL31_CONSOLE_ADDRESS = 0xFF000000
PM_CONFIG_HEADER = (2, 8, 1)


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _slice(data: bytes, offset: int, length: int, label: str) -> bytes:
    payload = data[offset : offset + length]
    if len(payload) != length:
        raise ValueError(f"{label} extends beyond BOOT.BIN")
    return payload


def _swap_words(data: bytes) -> bytes:
    if len(data) % 4:
        raise ValueError("PL partition length is not a multiple of four")
    return b"".join(data[i : i + 4][::-1] for i in range(0, len(data), 4))


def _atf_handoff(bl31_address: int, uboot_address: int) -> bytes:
    """Build the Xilinx FSBL-to-BL31 handoff table used by ZynqMP ATF."""
    header = struct.pack("<II", ATF_HANDOFF_MAGIC, 2)
    entries = struct.pack("<QQ", bl31_address, 0x1C)
    entries += struct.pack("<QQ", uboot_address, 0x10)
    entries += bytes((ATF_HANDOFF_MAX_ENTRIES - 2) * 16)
    return header + entries


def _patch_bl31_console(payload: bytes, destination: int) -> tuple[bytes, int]:
    source = struct.pack("<Q", DEFAULT_BL31_CONSOLE_ADDRESS)
    count = payload.count(source)
    if not count:
        raise ValueError("BL31 does not contain the expected 64-bit UART0 console base")
    return payload.replace(source, struct.pack("<Q", destination)), count


def _pm_config_length(words: tuple[int, ...], start: int) -> int:
    """Return a validated legacy ZynqMP XilPM configuration-object length."""
    index = start + words[start] + 1
    sections = words[start + 1]
    for _ in range(sections):
        section = words[index]
        index += 1
        if section == 0x101:  # masters: count + five words per master
            count = words[index]
            index += 1 + 5 * count
        elif section == 0x102:  # slaves: count + three words per slave
            count = words[index]
            index += 1 + 3 * count
        elif section == 0x103:  # prealloc: variable slave list per master
            masters = words[index]
            index += 1
            for _ in range(masters):
                count = words[index + 1]
                index += 2 + 4 * count
        elif section in (0x104, 0x105):  # power/reset: pairs
            count = words[index]
            index += 1 + 2 * count
        elif section == 0x107:  # base and overlay config permissions
            index += 2
        elif section == 0x106:  # shutdown permissions
            index += 1
        elif section == 0x108:  # GPO mask and initial state
            index += 2
        else:
            raise ValueError(f"unknown XilPM configuration section 0x{section:x}")
        if index > len(words):
            raise ValueError("XilPM configuration object extends beyond FSBL")
    return (index - start) * 4


def _extract_pm_config(fsbl: bytes) -> bytes:
    """Find and extract the production ``XPm_ConfigObject`` from raw FSBL."""
    usable = fsbl[: len(fsbl) & ~3]
    words = struct.unpack(f"<{len(usable) // 4}I", usable)
    candidates = []
    for index in range(len(words) - len(PM_CONFIG_HEADER) + 1):
        if words[index : index + len(PM_CONFIG_HEADER)] == PM_CONFIG_HEADER:
            try:
                length = _pm_config_length(words, index)
            except (IndexError, ValueError):
                continue
            candidates.append((index * 4, length))
    if len(candidates) != 1:
        raise ValueError(
            f"expected one legacy XilPM configuration object in FSBL, found {len(candidates)}"
        )
    offset, length = candidates[0]
    return fsbl[offset : offset + length]


def extract(
    boot_bin: Path,
    output_dir: Path,
    uboot_address: int = 0x08000000,
    bl31_console_address: int | None = None,
) -> dict:
    data = boot_bin.read_bytes()
    if len(data) < 0xA0:
        raise ValueError("file is too short to contain a ZynqMP boot header")

    source_offset = _u32(data, BOOT_SOURCE_OFFSET)
    pmufw_length = _u32(data, PMUFW_LENGTH_OFFSET)
    fsbl_length = _u32(data, FSBL_LENGTH_OFFSET)
    if not pmufw_length or not fsbl_length:
        raise ValueError("BOOT.BIN does not contain combined PMUFW + FSBL lengths")

    pmufw = _slice(data, source_offset, pmufw_length, "PMUFW")
    fsbl = _slice(data, source_offset + pmufw_length, fsbl_length, "FSBL")

    partitions = []
    pht = _u32(data, PHT_OFFSET)
    visited = set()
    while pht:
        if pht in visited:
            raise ValueError("partition-header chain contains a loop")
        visited.add(pht)
        _slice(data, pht, PHT_SIZE, "partition header")
        length = _u32(data, pht + 0x04) * 4
        next_pht = _u32(data, pht + 0x0C) * 4
        load_address = _u32(data, pht + 0x18) | (_u32(data, pht + 0x1C) << 32)
        offset = _u32(data, pht + 0x20) * 4
        attributes = _u32(data, pht + 0x24)
        if attributes & ENCRYPTION_MASK:
            raise ValueError("encrypted BOOT.BIN partitions are not supported")
        partitions.append(
            {
                "load_address": load_address,
                "attributes": attributes,
                "payload": _slice(data, offset, length, "partition"),
            }
        )
        pht = next_pht

    pl = next((p for p in partitions if p["attributes"] & DEST_DEVICE_MASK == DEST_DEVICE_PL), None)
    bl31 = next((p for p in partitions if p["load_address"] == BL31_ADDRESS), None)
    uboot = next((p for p in partitions if p["load_address"] == uboot_address), None)
    if pl is None:
        raise ValueError("no PL partition found")
    if uboot is None:
        raise ValueError(f"no partition loads at U-Boot address 0x{uboot_address:08x}")
    if bl31 is None:
        raise ValueError(f"no partition loads at BL31 address 0x{BL31_ADDRESS:08x}")

    output_dir.mkdir(parents=True, exist_ok=True)
    bl31_payload = bl31["payload"]
    console_patch_count = 0
    if bl31_console_address is not None:
        bl31_payload, console_patch_count = _patch_bl31_console(bl31_payload, bl31_console_address)
    payloads = {
        "pmufw.bin": pmufw,
        "fsbl.bin": fsbl,
        "pm-config-object.bin": _extract_pm_config(fsbl),
        "system-top-xsdb.bin": _swap_words(pl["payload"]),
        "bl31.bin": bl31_payload,
        "atf-handoff.bin": _atf_handoff(BL31_ADDRESS, uboot_address),
        "u-boot.bin": uboot["payload"],
    }
    manifest = {
        "source": str(boot_bin),
        "bl31_console_patch": {
            "from": DEFAULT_BL31_CONSOLE_ADDRESS,
            "to": bl31_console_address,
            "matches": console_patch_count,
        },
        "payloads": {},
    }
    for name, payload in payloads.items():
        (output_dir / name).write_bytes(payload)
        manifest["payloads"][name] = {
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("boot_bin", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--uboot-address", type=lambda value: int(value, 0), default=0x08000000)
    parser.add_argument(
        "--bl31-console-address",
        type=lambda value: int(value, 0),
        help="guardedly replace BL31's 64-bit UART0 console base (for example 0xff010000)",
    )
    args = parser.parse_args()
    manifest = extract(
        args.boot_bin,
        args.output_dir,
        args.uboot_address,
        args.bl31_console_address,
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
