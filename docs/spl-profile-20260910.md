# S7 raw / Semi-Falcon raw: SPL timing experiment (2026-09-10)

## Scope and baseline

Two matched SD/local-ext4-root variants, no NFS/eMMC/userspace changes.
S7 raw starts from 47e5290 (S7 config plus existing K0 load instrumentation).
Semi-Falcon starts from 633d221, retaining 0009 packaging and 0010 MCU R5FSS0
core1 cleanup. Only its gzip command and CONFIG_GZIP are removed for raw parity.
Existing branches, stashes and s7-raw-20260909 bundle are untouched.

Both variants retain all existing markers, the exact raw Image and kernel DTB
from artifacts/s7-raw-20260909, and SD mmc 1:2 local PARTUUID bootargs.
No Falcon Mode/tifalcon.bin is used. No kernel rebuild or userspace changes.

The TI FAQ demonstrates R5 SPL -> ATF -> OP-TEE -> full U-Boot for J7200 SDK
10.1. This experiment applies the same packaging to the existing SDK 11.02
optimized baseline with the already identified cleanup fix. It does not assume
that an example for another SDK proves hardware validation of these binaries.
https://e2e.ti.com/support/processors-group/processors/f/processors-forum/1547154/faq-dra821-spl-boot-without-a72-spl-on-j7200-on-10-1-sdk

## New measurements (microseconds)

| Marker | Capture point |
|---|---|
| R5_INIT_DONE_US | End of R5 board_init_f, after DDR/cache/NAVSS/QoS setup |
| R5_LOAD_START_US / R5_LOAD_DONE_US | Immediately around SPL loader->load_image, normally tispl.bin |
| R5_ARM64_REQUEST_US | Immediately before rproc_start(1), after image preparation |
| A72_SPL_ENTRY_US | Start of A72 SPL board_init_f C code |
| A72_SPL_INIT_DONE_US | End of A72 SPL board_init_f |
| A72_SPL_LOAD_START_US / A72_SPL_LOAD_DONE_US | Around A72 SPL loader->load_image, normally u-boot.img |
| A72_SPL_HANDOFF_US | After spl_board_prepare_for_boot, before jump_to_image |
| UBOOT_ENTRY_US | Start of full U-Boot board_init_f C code, before relocation |

SPL loader intervals include MMC probing, filesystem/header parsing, reads and
any authentication performed inside the loader. They are NOT pure storage read
bandwidth. The last attempted loader overwrites the loader interval; use successful
normal SD cold boots, not fallback/retry runs, for the benchmark.

R5 uses its existing timer_get_us timebase. A72 uses the existing seeded GTC
timer_get_boot_us timebase. No timer is initialized earlier or reset for these
markers. R5_ARM64_REQUEST_US is measured from that existing timer's origin: it
excludes ROM and any R5 startup before the timer began. It is an A72 release
request boundary, NOT the last R5 instruction: R5 continues into DM and overlaps
A72 execution. Do not sum overlapping processor lifetimes.

A72_SPL_HANDOFF_US - A72_SPL_ENTRY_US measures the SPL C-stage, excluding its
initial assembly and final branch. UBOOT_ENTRY_US - A72_SPL_HANDOFF_US is the
handoff gap, not another storage read. A72 SPL markers are absent (null), not
zero-duration, in Semi-Falcon. The R5->next-C-entry gap includes TF-A/OP-TEE,
reset-release and assembly startup, plus existing R5/GTC seed alignment error;
do not label it pure TF-A or pure OP-TEE time.

## Low-overhead transport and limits

No additional successful-boot UART output. Samples are buffered in MCU SRAM
0x41cffb7c..0x41cffbab, scratchpad offsets 384..431. Existing legacy metrics
remain at 0x41cffbec..0x41cffbfb (last 16 bytes). The TI EEPROM structure at the
scratchpad prefix is 84 bytes, so it does not overlap. A72 maps SRAM as Device;
R5 cache contents are flushed by the existing spl_board_prepare_for_boot
dcache_disable before A72 is started. The release marker is written afterward.
R5 resets the record on each cold boot, before loading the next stage.

The record is one big-endian DT property, /chosen/ti,spl-profile-v1, 48 bytes:
u32 magic 0x53504c31, u32 validity mask, then 10 u32 timestamps in table order.
Conventional mask: 0x3ff; Semi-Falcon mask: 0x20f. 32-bit microseconds wrap at
about 71 minutes; this tool rejects non-monotonic intervals. Not an LPM/resume
test. Export occurs beside existing DT metrics after BOOTLOADER_DONE sampling.
That extra FDT operation and timestamp stores have small nonzero overhead;
KERNEL_ENTRY_US includes the export and existing serial output. Compare these
two instrumented variants, not the instrumented one against an old uninstrumented
run as if instrumentation were free.

## Manual deployment (nothing is flashed by the build)

From the Yocto workspace, select exactly one bundle:

```sh
BUNDLE="$PWD/sources/meta-boot-time/artifacts/spl-profile-s7-raw-20260910"
# Or: BUNDLE="$PWD/sources/meta-boot-time/artifacts/spl-profile-semi-raw-20260910"
(cd "$BUNDLE" && sha256sum -c SHA256SUMS)
lsblk -o NAME,SIZE,MODEL,TRAN,FSTYPE,UUID,PARTUUID,MOUNTPOINTS
```

Identify the SD card by capacity/model and its existing mounts. Do not assume
/dev/sda is the SD card; the host's SATA disk must not be used. No partitioning
or formatting is required. Set the following to the verified existing SD mounts:

```sh
SD_BOOT=/actual/SD/boot/partition/mount
SD_ROOT=/actual/SD/root/partition/mount
findmnt --target "$SD_BOOT"
findmnt --target "$SD_ROOT"
BACKUP=$(mktemp -d "$PWD/sources/meta-boot-time/artifacts/sd-backup.XXXXXX")
sudo cp -a "$SD_BOOT/tiboot3.bin" "$SD_BOOT/tispl.bin" "$SD_BOOT/u-boot.img" "$BACKUP/"
sudo cp -a "$SD_ROOT/boot/Image" "$BACKUP/Image"
sudo cp -a "$SD_ROOT/boot/dtb/ti/k3-j7200-common-proc-board.dtb" "$BACKUP/"
sudo cp "$BUNDLE/tiboot3.bin" "$BUNDLE/tispl.bin" "$BUNDLE/u-boot.img" "$SD_BOOT/"
sudo cp "$BUNDLE/Image" "$SD_ROOT/boot/Image"
sudo cp "$BUNDLE/k3-j7200-common-proc-board.dtb" "$SD_ROOT/boot/dtb/ti/"
sudo cmp "$BUNDLE/tiboot3.bin" "$SD_BOOT/tiboot3.bin"
sudo cmp "$BUNDLE/tispl.bin" "$SD_BOOT/tispl.bin"
sudo cmp "$BUNDLE/u-boot.img" "$SD_BOOT/u-boot.img"
sudo cmp "$BUNDLE/Image" "$SD_ROOT/boot/Image"
sudo cmp "$BUNDLE/k3-j7200-common-proc-board.dtb" "$SD_ROOT/boot/dtb/ti/k3-j7200-common-proc-board.dtb"
sync
```

Unmount both SD partitions before removal. Backups permit restoring the previous
five files. Keep the existing SD boot switches and all other conditions unchanged.
For Semi-Falcon, full U-Boot is embedded in tispl.bin; u-boot.img is copied for
bundle consistency but normally is NOT loaded separately by that boot path.
Do not mix tiboot3/tispl/u-boot files from different bundles.

## Capture each cold boot

Capture the same UART with the same existing methodology, through KERNEL_ENTRY_US.
After Linux is running, retrieve the DT record WITHOUT adding a boot service:

```sh
# On target (or scp this existing property directly):
od -An -tx1 /proc/device-tree/chosen/ti,spl-profile-v1
```

```sh
# On host; replace target address with the actual board address:
scp root@BOARD_IP:/proc/device-tree/chosen/ti,spl-profile-v1 s7-run01.profile
python3 sources/meta-boot-time/tools/spl-profile.py s7-run01.profile --log s7-run01.uart.log
```

Use a record and UART log from the SAME boot. Preserve one pair per run. If SSH
is unavailable, save the property via an existing file-transfer method or capture
its `od` hex output; this is post-boot collection, not a measurement target change.
Expect all 10 markers for conventional and only R5 + UBOOT_ENTRY for Semi-Falcon.
Missing/wrong magic/size/mask means the expected chain did not publish a valid
record; check deployed hashes and errors before interpreting timing.

Use at least 10 alternating cold boots per variant. Compare medians and spread:
R5 loader duration, R5 preparation after load, A72 SPL C-stage and loader (only
conventional), full U-Boot entry to BOOTLOADER_DONE, raw kernel read duration,
and the original KERNEL_ENTRY_US endpoint. Semi-Falcon may increase R5 FIT loading
while eliminating A72 SPL and its separate U-Boot load; measure the net change.
Keep power-cycle method, SD, serial logging, raw Image, DTB, bootargs and filesystem
constant. No multi-user.target/userspace measurements are added.
