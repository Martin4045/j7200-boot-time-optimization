#!/bin/bash
# J7200: provision eMMC from the optimized SD rootfs, or update U-Boot only.
set -Eeuo pipefail

usage() {
    echo "Usage: bash $0 {install|update-uboot} [SD boot directory]"
    echo "Default source: /run/media/boot-mmcblk1p1"
    echo "install erases eMMC; update-uboot preserves the installed rootfs."
}
die() { echo "ERROR: $*" >&2; exit 1; }
case ${1:-} in
    -h|--help) usage; exit 0 ;;
    install|update-uboot) mode=$1 ;;
    *) usage; exit 2 ;;
esac
(( $# <= 2 )) || die "Too many arguments"
bootdir=${2:-/run/media/boot-mmcblk1p1}
disk=/dev/mmcblk0
boot=/dev/mmcblk0boot0
dest=/mnt/emmc-rootfs
mounted=0
writable=0

cleanup() {
    if (( writable )); then echo 1 > /sys/block/mmcblk0boot0/force_ro || true; fi
    if (( mounted )); then sync; umount "$dest" || true; fi
}
trap cleanup EXIT
trap 'echo "FAILED at line $LINENO. Do not switch to eMMC boot yet." >&2' ERR
trap 'exit 130' INT
trap 'exit 143' TERM

(( EUID == 0 )) || die "Run as root on the J7200 board"
for cmd in findmnt lsblk readlink stat dd sha256sum sync cat; do
    command -v "$cmd" >/dev/null || die "Missing command: $cmd"
done
[[ $(cat /sys/class/block/mmcblk0/device/type) == MMC ]] || die "mmcblk0 is not eMMC"
[[ -b $boot ]] || die "eMMC boot0 is missing"
rootdev=$(readlink -f "$(findmnt -n -o SOURCE /)")
[[ $rootdev == /dev/mmcblk1p2 || $rootdev == /dev/mmcblk0p2 ]] || die "Unexpected root device: $rootdev"

check_image() {
    local file=$1 limit=$2 size
    [[ -s $bootdir/$file ]] || die "Missing $bootdir/$file"
    size=$(stat -Lc %s "$bootdir/$file")
    (( size <= limit )) || die "$file exceeds its boot0 slot"
    sha256sum "$bootdir/$file"
}
check_image u-boot.img $((4 * 1024 * 1024))

if [[ $mode == install ]]; then
    [[ $rootdev == /dev/mmcblk1p2 ]] || die "Initial installation requires SD rootfs"
    [[ $(cat /sys/class/block/mmcblk1/device/type) == SD ]] || die "mmcblk1 is not SD"
    for cmd in sfdisk mkfs.ext4 mount umount mountpoint udevadm tar du blockdev mmc grep tr awk chmod mkdir; do
        command -v "$cmd" >/dev/null || die "Missing command: $cmd"
    done
    tar --version | grep -q 'GNU tar' || die "GNU tar is required"
    [[ -z $(lsblk -nr -o MOUNTPOINTS "$disk" | tr -d '[:space:]') ]] || die "eMMC has mounted filesystems"
    mountpoint -q "$dest" && die "$dest is already mounted"
    [[ ! -L $dest ]] || die "Mount directory must not be a symlink"
    for path in /boot /usr /var; do
        [[ $(readlink -f "$(findmnt -n -o SOURCE -T "$path")") == "$rootdev" ]] || die "$path is on a separate filesystem; automatic copying is not supported"
    done
    [[ -s /boot/Image && -s /boot/dtb/ti/k3-j7200-common-proc-board.dtb ]] || die "Kernel or DTB missing"
    [[ -x /lib/systemd/systemd ]] || die "Rootfs init executable missing"
    check_image tiboot3.bin $((1024 * 1024))
    check_image tispl.bin $((2 * 1024 * 1024))
    used=$(du -sx -B1 / | awk '{print $1}')
    capacity=$(blockdev --getsize64 "$disk")
    (( used + 2 * 1024 * 1024 * 1024 < capacity )) || die "Insufficient eMMC space (requires 2 GiB headroom)"
    echo "Erase $disk, copy SD rootfs, and overwrite $boot with the three listed bootloaders."
    echo "Stop applications writing persistent data before continuing."
else
    echo "Overwrite only $boot at offset 0x300000 with the listed u-boot.img."
fi
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS "$disk"
read -r -p 'Type mmcblk0 to proceed: ' answer
[[ $answer == mmcblk0 ]] || die "Cancelled"

if [[ $mode == install ]]; then
    sfdisk "$disk" <<'EOF'
label: dos
unit: sectors

start=2048, size=262144, type=83
start=264192, type=83
EOF
    udevadm settle
    [[ -b ${disk}p1 && -b ${disk}p2 ]] || die "Partition devices missing"
    mkfs.ext4 -L emmc-data "${disk}p1"
    mkfs.ext4 -L emmc-rootfs "${disk}p2"
    mkdir -p "$dest"
    mount "${disk}p2" "$dest"
    mounted=1
    echo "Copying rootfs; this can take several minutes..."
    # Exclude entire virtual mountpoints, including their changing metadata.
    tar --one-file-system --numeric-owner --acls --xattrs --sparse \
        --exclude='./dev' --exclude='./proc' --exclude='./sys' \
        --exclude='./run' --exclude='./tmp' --exclude='./mnt' \
        --exclude='./media' --exclude='./lost+found' \
        -C / -cpf - . |
        tar --numeric-owner --acls --xattrs --same-owner --same-permissions \
            --warning=no-timestamp -C "$dest" -xpf -
    mkdir -p "$dest"/{dev,proc,sys,run,tmp,mnt,media}
    chmod 0755 "$dest"/{dev,proc,sys,run,mnt,media}
    chmod 1777 "$dest/tmp"
    for file in /boot/Image /boot/dtb/ti/k3-j7200-common-proc-board.dtb /lib/systemd/systemd; do
        a=$(sha256sum "$file"); b=$(sha256sum "$dest$file")
        [[ ${a%% *} == "${b%% *}" ]] || die "Rootfs verification failed: $file"
    done
    [[ -x $dest/lib/systemd/systemd ]] || die "Copied init is not executable"
    echo "Rootfs, kernel, DTB and init verified."
fi

write_image() {
    local file=$1 sector=$2 size whole rest a b
    size=$(stat -Lc %s "$bootdir/$file")
    dd if="$bootdir/$file" of="$boot" bs=512 seek="$sector" conv=notrunc,fsync
    whole=$((size / 512)); rest=$((size % 512))
    a=$(sha256sum "$bootdir/$file")
    # Exact-length read avoids BusyBox cmp -i and pipe SIGPIPE issues.
    b=$({
        dd if="$boot" bs=512 skip="$sector" count="$whole" 2>/dev/null || return 1
        if (( rest )); then
            dd if="$boot" bs=1 skip="$((sector * 512 + whole * 512))" count="$rest" 2>/dev/null || return 1
        fi
    } | sha256sum)
    [[ ${a%% *} == "${b%% *}" ]] || die "boot0 verification failed: $file"
    echo "$file: WRITE AND SHA256 VERIFY OK"
}
writable=1
echo 0 > /sys/block/mmcblk0boot0/force_ro
if [[ $mode == install ]]; then
    write_image tiboot3.bin 0
    write_image tispl.bin 2048
fi
write_image u-boot.img 6144
echo 1 > /sys/block/mmcblk0boot0/force_ro
writable=0

if [[ $mode == install ]]; then
    mmc bootbus set single_backward x1 x8 "$disk"
    mmc bootpart enable 1 1 "$disk"
    mmc extcsd read "$disk" | grep -A5 -E 'PARTITION_CONFIG|BOOT_BUS_CONDITIONS'
fi
sync
if (( mounted )); then umount "$dest"; mounted=0; fi
echo "SUCCESS. Run poweroff, remove power and SD, then select eMMC boot:"
echo "SW8: only 1 ON. SW9: only 2 ON. SW3.1 stays OFF."
echo "After powering on without SD, verify: findmnt / (expected /dev/mmcblk0p2)."
