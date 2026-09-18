#!/usr/bin/env python3
"""Create a J7200 HyperFlash boot update directory from Yocto deploy files."""

from __future__ import annotations

import argparse
import hashlib
import json
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def make_flash_script(output: Path) -> Path:
    command_file = output / "flash-hyperflash.cmd"
    its_file = output / "flash-hyperflash.its"
    script_file = output / "flash-hyperflash.scr"
    command_file.write_text(
        """echo J7200 HyperFlash update started
setenv mtdparts 'mtdparts=47034000.hyperbus:1m(hbmc.tiboot3),2m(hbmc.tispl),4m(hbmc.u-boot),256k(hbmc.env),-@8m(hbmc.rootfs)'
mtd list

echo Writing Linux Image and DTB bundle
if fatload mmc 1:1 ${loadaddr} hf-kernel-dtb.bin; then
    if test ${filesize} = 1840000; then
        if mtd erase hbmc.rootfs 0 0x1840000 && mtd write hbmc.rootfs ${loadaddr} 0 ${filesize} && cmp.b ${loadaddr} 0x500800000 ${filesize}; then
            echo Linux Image and DTB verified
        else
            echo ERROR: Linux Image and DTB update failed
            exit
        fi
    else
        echo ERROR: invalid hf-kernel-dtb.bin size
        exit
    fi
else
    echo ERROR: cannot load hf-kernel-dtb.bin
    exit
fi

echo Writing u-boot.img
if fatload mmc 1:1 ${loadaddr} hf-u-boot.img; then
    if mtd erase hbmc.u-boot && mtd write hbmc.u-boot ${loadaddr} 0 ${filesize} && cmp.b ${loadaddr} 0x500300000 ${filesize}; then
        echo u-boot.img verified
    else
        echo ERROR: u-boot.img update failed
        exit
    fi
else
    echo ERROR: cannot load u-boot.img
    exit
fi

echo Writing tispl.bin
if fatload mmc 1:1 ${loadaddr} hf-tispl.bin; then
    if mtd erase hbmc.tispl && mtd write hbmc.tispl ${loadaddr} 0 ${filesize} && cmp.b ${loadaddr} 0x500100000 ${filesize}; then
        echo tispl.bin verified
    else
        echo ERROR: tispl.bin update failed
        exit
    fi
else
    echo ERROR: cannot load tispl.bin
    exit
fi

echo Writing tiboot3.bin last
if fatload mmc 1:1 ${loadaddr} hf-tiboot3.bin; then
    if mtd erase hbmc.tiboot3 && mtd write hbmc.tiboot3 ${loadaddr} 0 ${filesize} && cmp.b ${loadaddr} 0x500000000 ${filesize}; then
        echo tiboot3.bin verified
    else
        echo ERROR: tiboot3.bin update failed
        exit
    fi
else
    echo ERROR: cannot load tiboot3.bin
    exit
fi

echo HyperFlash update completed successfully
""",
        encoding="ascii",
    )

    mkimage = shutil.which("mkimage")
    if not mkimage:
        raise SystemExit("mkimage was not found; install u-boot-tools")
    its_file.write_text(
        f'''/dts-v1/;

/ {{
    description = "J7200 HyperFlash update";
    #address-cells = <1>;

    images {{
        script {{
            description = "Write and verify J7200 HyperFlash";
            data = /incbin/("{command_file}");
            type = "script";
            arch = "arm64";
            compression = "none";
            hash-1 {{
                algo = "sha256";
            }};
        }};
    }};

    configurations {{
        default = "conf-1";
        conf-1 {{
            script = "script";
        }};
    }};
}};
''',
        encoding="ascii",
    )
    try:
        subprocess.run(
            [mkimage, "-f", str(its_file), str(script_file)], check=True
        )
    finally:
        its_file.unlink(missing_ok=True)
    return script_file


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deploy", type=Path, default=DEFAULT_DEPLOY)
    parser.add_argument(
        "--output", type=Path, default=Path("hyperflash-update")
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
    script_path = make_flash_script(output)

    generated = [
        output / "hf-tiboot3.bin",
        output / "hf-tispl.bin",
        output / "hf-u-boot.img",
        bundle_path,
        script_path,
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


if __name__ == "__main__":
    main()
