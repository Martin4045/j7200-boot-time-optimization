#!/usr/bin/env python3
"""Read-only static checks of the two archived SPL profile variants."""
from pathlib import Path
import hashlib

layer = Path(__file__).resolve().parents[1]
old = layer / "artifacts/s7-raw-20260909"
s7 = layer / "artifacts/spl-profile-s7-raw-20260910"
semi = layer / "artifacts/spl-profile-semi-raw-20260910"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def config(path):
    return dict(line.split("=", 1) for line in path.read_text().splitlines()
                if line.startswith("CONFIG_") and "=" in line)


for cpu in ("a72", "r5"):
    assert (s7 / f"{cpu}.config").read_bytes() == (old / f"{cpu}.config").read_bytes()
    a, b = config(s7 / f"{cpu}.config"), config(semi / f"{cpu}.config")
    changed = {k: (a.get(k), b.get(k)) for k in a.keys() | b.keys() if a.get(k) != b.get(k)}
    assert changed == ({k: ("0x80800000", "0x80080000") for k in
                        ("CONFIG_TEXT_BASE", "CONFIG_SYS_UBOOT_START")} if cpu == "a72" else {})
    print(f"PASS {cpu}: S7 .config byte-identical to original; paired differences: {changed}")

for bundle in (s7, semi):
    for file in ("Image", "k3-j7200-common-proc-board.dtb"):
        assert sha(bundle / file) == sha(old / file)
    c = config(bundle / "a72.config")
    cmd = c["CONFIG_BOOTCOMMAND"].strip('"')
    assert cmd == config(old / "a72.config")["CONFIG_BOOTCOMMAND"].strip('"')
    assert " /boot/Image &&" in cmd and "booti 0x82000000 - 0x88000000" in cmd
    assert cmd.encode() in (bundle / "u-boot.img").read_bytes()
    assert '#define CONFIG_BOOTCOMMAND ' + c["CONFIG_BOOTCOMMAND"] in (bundle / "static/a72-autoconf.h").read_text()
    for bad in (b"Image.gz", b"kernel_comp_addr_r", b"kernel_comp_size"):
        assert bad.decode() not in cmd
        # Generic booti code can retain variable-name strings even in the
        # original raw baseline. They are not assignments in the environment.
        assert (bad in (bundle / "u-boot.img").read_bytes()) == (bad in (old / "u-boot.img").read_bytes())
    for assignment in (b"kernel_comp_addr_r=", b"kernel_comp_size="):
        assert assignment not in (bundle / "u-boot.img").read_bytes()
    assert c.get("CONFIG_GZIP") != "y" and c.get("CONFIG_SPL_OS_BOOT") != "y"
    for marker in (b"BOOTLOADER_DONE_US", b"KERNEL_LOAD_START_US", b"KERNEL_LOAD_DONE_US",
                   b"KERNEL_BOOTI_START_US", b"KERNEL_DECOMP_START_US", b"KERNEL_DECOMP_DONE_US",
                   b"ti,spl-profile-v1"):
        assert marker in (bundle / "u-boot.img").read_bytes(), marker
    assert b"R5_GTC_SEED_US" in (bundle / "tiboot3.bin").read_bytes()
    assert b"KERNEL_ENTRY_US" in (bundle / "Image").read_bytes()
    fit = (bundle / "static/tispl-fit.txt").read_text()
    assert ("Image 3 (spl)" in fit) == (bundle == s7)
    assert ("Image 3 (uboot)" in fit) == (bundle == semi)
    print(f"PASS {bundle.name}: raw/DTB identity, bootcmd, legacy markers, new property, FIT stage")
    for file in ("tiboot3.bin", "tispl.bin", "u-boot.img", "Image", "k3-j7200-common-proc-board.dtb"):
        print(f"  {file}: {(bundle / file).stat().st_size} bytes sha256={sha(bundle / file)}")

assert "shutdown_mcu_r5_core1" in (semi / "static/evm.c").read_text()
assert "Unable to shutdown MCU R5 core 1" in (semi / "u-boot.img").read_bytes().decode("latin1")
print("PASS Semi-Falcon: core1 cleanup source and error string retained (runtime success requires board test)")
print("Hardware validation: NOT performed. No timing improvement is claimed before paired cold-boot captures.")
