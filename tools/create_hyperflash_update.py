#!/usr/bin/env python3
"""Create a J7200 HyperFlash boot update directory from Yocto deploy files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path


DEFAULT_DEPLOY = Path(
    "/mnt/mydisk/dasan/yocto-build/build/deploy-ti/images/j7200-evm"
)

IMAGE_SLOT_SIZE = 0x01800000       # 24 MiB
DTB_SLOT_OFFSET = 0x01800000       # hbmc.rootfs-relative
DTB_SLOT_SIZE = 0x00040000         # 256 KiB, one HyperFlash erase block
BUNDLE_SIZE = DTB_SLOT_OFFSET + DTB_SLOT_SIZE

LIMITS = {
    "tiboot3.bin": 0x00100000,
    "tispl.bin": 0x00200000,
    "u-boot.img": 0x00400000,
    "Image": IMAGE_SLOT_SIZE,
    "k3-j7200-common-proc-board.dtb": DTB_SLOT_SIZE,
}

INITIAL_ENV = "u-boot-ti-staging-initial-env-j7200-evm"
REQUIRED_ENV_LINES = (
    "bootdelay=0",
    "bootcmd=run bootcmd_hbmc_emmc",
    "bootcmd_hbmc_emmc=",
    "hbmc_kernel_addr=0x500800000",
    "hbmc_fdt_addr=0x502000000",
)

SD_UPDATE_FILES = (
    "hf-tiboot3.bin",
    "hf-tispl.bin",
    "hf-u-boot.img",
    "hf-kernel-dtb.bin",
    "flash-hyperflash.cmd",
    "flash-hyperflash.env",
    "manifest.json",
)

UPDATE_ENV_VARS = (
    "hf_setup",
    "hf_kernel",
    "hf_uboot",
    "hf_tispl",
    "hf_tiboot3",
    "hf_update",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_command(args: list[str]) -> str:
    try:
        result = subprocess.run(
            args, check=True, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
    except FileNotFoundError:
        raise SystemExit(f"Required command was not found: {args[0]}")
    except subprocess.CalledProcessError as error:
        output = error.stdout.strip() if error.stdout else "no output"
        raise SystemExit(f"Command failed: {' '.join(args)}\n{output}")
    return result.stdout.strip()


def lsblk_devices() -> tuple[list[dict], dict[str, dict]]:
    output = run_command([
        "lsblk", "--json", "-o",
        "NAME,PATH,PKNAME,TYPE,FSTYPE,LABEL,MOUNTPOINTS,RM,RO,TRAN,SIZE",
    ])
    roots = json.loads(output)["blockdevices"]
    flat: dict[str, dict] = {}

    def visit(node: dict, disk: dict, inherited_removable: bool) -> None:
        item = dict(node)
        removable = bool(item.get("rm")) or inherited_removable
        item["removable"] = removable
        item["disk_path"] = disk["path"]
        flat[item["path"]] = item
        for child in item.get("children") or []:
            visit(child, disk, removable)

    for root in roots:
        visit(root, root, bool(root.get("rm")))
    return roots, flat


def select_sd_partition(requested: str | None) -> tuple[Path, Path]:
    _, devices = lsblk_devices()
    fat_types = {"vfat", "fat", "fat16", "fat32"}

    def valid(item: dict) -> bool:
        return (
            item.get("type") == "part"
            and str(item.get("fstype") or "").lower() in fat_types
            and item.get("removable")
            and not item.get("ro")
        )

    if requested:
        requested_path = str(Path(requested).resolve())
        item = devices.get(requested_path)
        if not item:
            raise SystemExit(f"SD partition does not exist: {requested}")
        if not valid(item):
            raise SystemExit(
                f"Refusing {requested}: it must be a writable FAT partition "
                "on a removable disk"
            )
        return Path(item["path"]), Path(item["disk_path"])

    candidates = [item for item in devices.values() if valid(item)]
    boot_labeled = [
        item for item in candidates
        if str(item.get("label") or "").casefold() == "boot"
    ]
    selected = boot_labeled if boot_labeled else candidates
    if len(selected) != 1:
        found = "\n  ".join(
            f"{item['path']} label={item.get('label') or '-'} "
            f"size={item.get('size') or '-'}"
            for item in candidates
        ) or "none"
        raise SystemExit(
            "Could not uniquely identify the removable FAT boot partition.\n"
            f"Candidates:\n  {found}\n"
            "Insert one SD card or pass --sd-device /dev/sdX1."
        )
    item = selected[0]
    return Path(item["path"]), Path(item["disk_path"])


def mounted_target(device: Path) -> tuple[Path | None, bool]:
    result = subprocess.run(
        ["findmnt", "-rn", "-S", str(device), "-o", "TARGET,OPTIONS"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    if result.returncode:
        return None, False
    line = result.stdout.strip().splitlines()[0]
    target, options = line.split(maxsplit=1)
    return Path(target), "rw" in options.split(",")


def mount_sd_partition(device: Path) -> Path:
    target, writable = mounted_target(device)
    if target and writable:
        return target
    if target:
        run_command(["udisksctl", "unmount", "-b", str(device)])
    run_command(["udisksctl", "mount", "-b", str(device), "-o", "rw,flush"])
    target, writable = mounted_target(device)
    if not target or not writable:
        raise SystemExit(f"Failed to mount {device} read-write")
    return target


def copy_and_verify_sd(output: Path, mountpoint: Path) -> None:
    sources = [output / name for name in SD_UPDATE_FILES]
    missing = [str(path) for path in sources if not path.is_file()]
    if missing:
        raise SystemExit("Missing generated file(s):\n  " + "\n  ".join(missing))

    required = sum(path.stat().st_size for path in sources)
    free = shutil.disk_usage(mountpoint).free
    if free < required:
        raise SystemExit(
            f"Not enough free space on {mountpoint}: "
            f"need {required} bytes, have {free} bytes"
        )

    for source in sources:
        destination = mountpoint / source.name
        temporary = mountpoint / f".{source.name}.tmp"
        temporary.unlink(missing_ok=True)
        with source.open("rb") as src, temporary.open("wb") as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        os.replace(temporary, destination)

    os.sync()
    failures = []
    for source in sources:
        destination = mountpoint / source.name
        if source.stat().st_size != destination.stat().st_size:
            failures.append(f"{source.name}: size mismatch")
        elif sha256(source) != sha256(destination):
            failures.append(f"{source.name}: SHA-256 mismatch")
    if failures:
        raise SystemExit("SD verification failed:\n  " + "\n  ".join(failures))


def eject_sd(disk: Path) -> None:
    roots, _ = lsblk_devices()
    disk_node = next((item for item in roots if item.get("path") == str(disk)), None)
    if not disk_node:
        raise SystemExit(f"Cannot find SD disk for safe removal: {disk}")

    partitions = []

    def collect(node: dict) -> None:
        for child in node.get("children") or []:
            collect(child)
            if child.get("type") == "part":
                partitions.append(Path(child["path"]))

    collect(disk_node)
    os.sync()
    for partition in partitions:
        target, _ = mounted_target(partition)
        if target:
            run_command(["udisksctl", "unmount", "-b", str(partition)])
    run_command(["udisksctl", "power-off", "-b", str(disk)])


def require_artifacts(deploy: Path) -> dict[str, Path]:
    artifacts = {name: deploy / name for name in LIMITS}
    missing = [str(path) for path in artifacts.values() if not path.is_file()]
    if missing:
        raise SystemExit("Missing deploy artifact(s):\n  " + "\n  ".join(missing))

    for name, path in artifacts.items():
        size = path.stat().st_size
        if size == 0 or size > LIMITS[name]:
            raise SystemExit(
                f"{name}: size 0x{size:x} exceeds slot 0x{LIMITS[name]:x}"
            )
    return artifacts


def verify_uboot_environment(deploy: Path) -> Path:
    path = deploy / INITIAL_ENV
    if not path.is_file():
        raise SystemExit(f"Missing U-Boot initial environment: {path}")

    environment = path.read_text(encoding="utf-8", errors="replace")
    missing = [line for line in REQUIRED_ENV_LINES if line not in environment]
    if missing:
        raise SystemExit(
            "The deploy directory contains an old U-Boot build. "
            "Rebuild after applying patch 0005:\n\n"
            "  cd /mnt/mydisk/dasan/yocto-build/build\n"
            "  MACHINE=j7200-evm bitbake tisdk-default-image\n\n"
            "Missing from the deployed U-Boot environment:\n  "
            + "\n  ".join(missing)
        )
    return path


def make_bundle(image: Path, dtb: Path, output: Path) -> None:
    bundle = bytearray(b"\xff" * BUNDLE_SIZE)
    image_data = image.read_bytes()
    dtb_data = dtb.read_bytes()
    bundle[0 : len(image_data)] = image_data
    bundle[DTB_SLOT_OFFSET : DTB_SLOT_OFFSET + len(dtb_data)] = dtb_data
    output.write_bytes(bundle)


def make_flash_environment(output: Path) -> Path:
    command_file = output / "flash-hyperflash.cmd"
    environment_file = output / "flash-hyperflash.env"
    variables = {
        "hf_setup": (
            "echo J7200 HyperFlash update started; "
            "setenv mtdparts 'mtdparts=47034000.hyperbus:"
            "1m(hbmc.tiboot3),2m(hbmc.tispl),4m(hbmc.u-boot),"
            "256k(hbmc.env),-@8m(hbmc.rootfs)'; mtd list"
        ),
        "hf_kernel": (
            "echo Writing Linux Image and DTB bundle; "
            "if fatload mmc 1:1 ${loadaddr} hf-kernel-dtb.bin; then "
            "if test ${filesize} = 1840000; then "
            "if mtd erase hbmc.rootfs 0 0x1840000 && "
            "mtd write hbmc.rootfs ${loadaddr} 0 ${filesize} && "
            "cmp.b ${loadaddr} 0x500800000 ${filesize}; then "
            "echo Linux Image and DTB verified; else "
            "echo ERROR: Linux Image and DTB update failed; test 0 = 1; fi; "
            "else echo ERROR: invalid hf-kernel-dtb.bin size; test 0 = 1; fi; "
            "else echo ERROR: cannot load hf-kernel-dtb.bin; test 0 = 1; fi"
        ),
        "hf_uboot": (
            "echo Writing u-boot.img; "
            "if fatload mmc 1:1 ${loadaddr} hf-u-boot.img; then "
            "if mtd erase hbmc.u-boot && "
            "mtd write hbmc.u-boot ${loadaddr} 0 ${filesize} && "
            "cmp.b ${loadaddr} 0x500300000 ${filesize}; then "
            "echo u-boot.img verified; else "
            "echo ERROR: u-boot.img update failed; test 0 = 1; fi; "
            "else echo ERROR: cannot load hf-u-boot.img; test 0 = 1; fi"
        ),
        "hf_tispl": (
            "echo Writing tispl.bin; "
            "if fatload mmc 1:1 ${loadaddr} hf-tispl.bin; then "
            "if mtd erase hbmc.tispl && "
            "mtd write hbmc.tispl ${loadaddr} 0 ${filesize} && "
            "cmp.b ${loadaddr} 0x500100000 ${filesize}; then "
            "echo tispl.bin verified; else "
            "echo ERROR: tispl.bin update failed; test 0 = 1; fi; "
            "else echo ERROR: cannot load hf-tispl.bin; test 0 = 1; fi"
        ),
        "hf_tiboot3": (
            "echo Writing tiboot3.bin last; "
            "if fatload mmc 1:1 ${loadaddr} hf-tiboot3.bin; then "
            "if mtd erase hbmc.tiboot3 && "
            "mtd write hbmc.tiboot3 ${loadaddr} 0 ${filesize} && "
            "cmp.b ${loadaddr} 0x500000000 ${filesize}; then "
            "echo tiboot3.bin verified; else "
            "echo ERROR: tiboot3.bin update failed; test 0 = 1; fi; "
            "else echo ERROR: cannot load hf-tiboot3.bin; test 0 = 1; fi"
        ),
        "hf_update": (
            "run hf_setup && run hf_kernel && run hf_uboot && "
            "run hf_tispl && run hf_tiboot3 && "
            "echo HyperFlash update completed successfully"
        ),
    }
    environment_file.write_text(
        "".join(f"{name}={variables[name]}\n" for name in UPDATE_ENV_VARS),
        encoding="ascii",
    )
    import_vars = " ".join(UPDATE_ENV_VARS)
    command_file.write_text(
        "fatload mmc 1:1 ${scriptaddr} flash-hyperflash.env\n"
        f"env import -t ${{scriptaddr}} ${{filesize}} {import_vars}\n"
        "run hf_update\n",
        encoding="ascii",
    )
    return environment_file


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deploy", type=Path, default=DEFAULT_DEPLOY)
    parser.add_argument(
        "--output", type=Path, default=Path("hyperflash-update")
    )
    parser.add_argument(
        "--sd-device", metavar="/dev/sdX1",
        help="removable FAT boot partition; auto-detected by default",
    )
    parser.add_argument(
        "--no-sd-copy", action="store_true",
        help="only create the update bundle",
    )
    parser.add_argument(
        "--keep-sd-mounted", action="store_true",
        help="do not unmount and power off the SD card after verification",
    )
    args = parser.parse_args()

    deploy = args.deploy.resolve()
    output = args.output.resolve()
    artifacts = require_artifacts(deploy)
    initial_env = verify_uboot_environment(deploy)
    output.mkdir(parents=True, exist_ok=True)

    managed_outputs = (
        "tiboot3.bin",
        "tispl.bin",
        "u-boot.img",
        "hyperflash-kernel-dtb.bin",
        "hf-tiboot3.bin",
        "hf-tispl.bin",
        "hf-u-boot.img",
        "hf-kernel-dtb.bin",
        "flash-hyperflash.cmd",
        "flash-hyperflash.its",
        "flash-hyperflash.scr",
        "flash-hyperflash.env",
        "manifest.json",
    )
    for name in managed_outputs:
        path = output / name
        if path.is_file() or path.is_symlink():
            path.unlink()

    staged_bootloaders = {
        "tiboot3.bin": "hf-tiboot3.bin",
        "tispl.bin": "hf-tispl.bin",
        "u-boot.img": "hf-u-boot.img",
    }
    for source_name, output_name in staged_bootloaders.items():
        shutil.copyfile(artifacts[source_name], output / output_name)

    bundle_path = output / "hf-kernel-dtb.bin"
    make_bundle(
        artifacts["Image"],
        artifacts["k3-j7200-common-proc-board.dtb"],
        bundle_path,
    )
    environment_path = make_flash_environment(output)

    generated = [
        output / "hf-tiboot3.bin",
        output / "hf-tispl.bin",
        output / "hf-u-boot.img",
        bundle_path,
        output / "flash-hyperflash.cmd",
        environment_path,
    ]
    manifest = {
        "layout": {
            "hyperflash_base": "0x500000000",
            "kernel_flash_offset": "0x00800000",
            "kernel_slot_size": f"0x{IMAGE_SLOT_SIZE:x}",
            "dtb_flash_offset": "0x02000000",
            "dtb_slot_size": f"0x{DTB_SLOT_SIZE:x}",
            "rootfs": "eMMC partition 2",
        },
        "inputs": {
            name: {
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }
            for name, path in artifacts.items()
        },
        "u_boot_initial_environment": {
            "name": initial_env.name,
            "sha256": sha256(initial_env),
        },
        "outputs": {
            path.name: {
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in generated
        },
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Created: {output}")
    print(f"Image: 0x{artifacts['Image'].stat().st_size:x} / 0x{IMAGE_SLOT_SIZE:x}")
    print(
        "DTB:   "
        f"0x{artifacts['k3-j7200-common-proc-board.dtb'].stat().st_size:x} "
        f"/ 0x{DTB_SLOT_SIZE:x}"
    )
    print(f"Bundle: 0x{bundle_path.stat().st_size:x}")

    if not args.no_sd_copy:
        partition, disk = select_sd_partition(args.sd_device)
        mountpoint = mount_sd_partition(partition)
        print(f"SD boot partition: {partition} mounted at {mountpoint}")
        copy_and_verify_sd(output, mountpoint)
        print("SD copy and SHA-256 verification: PASS")
        if args.keep_sd_mounted:
            print(f"SD card remains mounted at {mountpoint}")
        else:
            eject_sd(disk)
            print(f"SD card is safe to remove: {disk}")


if __name__ == "__main__":
    main()
