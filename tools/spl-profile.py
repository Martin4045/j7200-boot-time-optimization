#!/usr/bin/env python3
"""Decode buffered J7200 SPL markers; run on the host, not in the boot path."""
import argparse
import json
import re
import struct
from pathlib import Path

NAMES = (
    "R5_INIT_DONE_US", "R5_LOAD_START_US", "R5_LOAD_DONE_US",
    "R5_ARM64_REQUEST_US", "A72_SPL_ENTRY_US", "A72_SPL_INIT_DONE_US",
    "A72_SPL_LOAD_START_US", "A72_SPL_LOAD_DONE_US", "A72_SPL_HANDOFF_US",
    "UBOOT_ENTRY_US",
)


def decode(data):
    if len(data) != 48:
        raise ValueError(f"expected 48 profile bytes, got {len(data)}")
    magic, valid, *values = struct.unpack(">12I", data)
    if magic != 0x53504C31 or valid & ~0x3FF:
        raise ValueError("invalid SPL profile v1 header")
    return {name: value if valid & (1 << i) else None
            for i, (name, value) in enumerate(zip(NAMES, values))}


def intervals(m):
    def delta(end, start):
        a, b = m.get(end), m.get(start)
        if a is None or b is None:
            return None
        if a < b:
            raise ValueError(f"non-monotonic timestamps: {start} -> {end}")
        return a - b

    result = {
        "R5_TIMER_ORIGIN_TO_ARM64_REQUEST_US": m["R5_ARM64_REQUEST_US"],
        "R5_IMAGE_LOADER_US": delta("R5_LOAD_DONE_US", "R5_LOAD_START_US"),
        "R5_AFTER_LOAD_TO_ARM64_REQUEST_US": delta("R5_ARM64_REQUEST_US", "R5_LOAD_DONE_US"),
        "A72_SPL_C_STAGE_US": delta("A72_SPL_HANDOFF_US", "A72_SPL_ENTRY_US"),
        "A72_SPL_INIT_US": delta("A72_SPL_INIT_DONE_US", "A72_SPL_ENTRY_US"),
        "A72_SPL_IMAGE_LOADER_US": delta("A72_SPL_LOAD_DONE_US", "A72_SPL_LOAD_START_US"),
        "UBOOT_C_ENTRY_TO_DONE_US": delta("BOOTLOADER_DONE_US", "UBOOT_ENTRY_US"),
        "RAW_IMAGE_READ_US": delta("KERNEL_LOAD_DONE_US", "KERNEL_LOAD_START_US"),
        "BOOTLOADER_DONE_TO_KERNEL_C_ENTRY_US": delta("KERNEL_ENTRY_US", "BOOTLOADER_DONE_US"),
    }
    # Cross-domain R5 -> GTC gaps include the existing seed calibration error.
    endpoint = "A72_SPL_ENTRY_US" if m["A72_SPL_ENTRY_US"] is not None else "UBOOT_ENTRY_US"
    result["ARM64_REQUEST_TO_NEXT_C_ENTRY_US"] = delta(endpoint, "R5_ARM64_REQUEST_US")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("profile", type=Path, help="copy of /proc/device-tree/chosen/ti,spl-profile-v1")
    p.add_argument("--log", type=Path, help="UART log from the SAME cold boot")
    a = p.parse_args()
    try:
        m = decode(a.profile.read_bytes())
        if a.log:
            entries = re.findall(r"BOOT_METRIC:\s*([A-Z0-9_]+_US)=(\d+)", a.log.read_text(errors="replace"))
            for name, value in entries:
                if name in m:
                    raise ValueError(f"duplicate marker {name}; use exactly one cold boot")
                m[name] = int(value)
        print(json.dumps({"markers_us": m, "intervals_us": intervals(m)}, indent=2))
    except (OSError, ValueError) as e:
        p.error(str(e))


if __name__ == "__main__":
    main()
