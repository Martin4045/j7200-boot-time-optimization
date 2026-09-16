#!/usr/bin/env bash
set -euo pipefail

build_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../build" && pwd -P)
image="$build_dir/deploy-ti/images/j7200-evm/tisdk-default-image-j7200-evm.rootfs.wic.xz"
device=/dev/sdc

usage() {
    printf '사용법: %s\n' "$0"
    printf '/dev/sdc의 마운트를 해제하고 확인 질문 없이 이미지를 기록합니다. 기존 데이터는 삭제됩니다.\n'
}

fail() {
    printf '오류: %s\n' "$*" >&2
    exit 1
}

if [[ ${1:-} == --help || ${1:-} == -h ]]; then
    usage
    exit 0
fi
if [[ $# -ne 0 ]]; then
    usage >&2
    exit 1
fi

# Already-unmounted devices may make umount return nonzero.
# check_unmounted below still prevents writing to any mounted device.
sudo -v
sudo umount /dev/sdc* || true

for tool in lsblk xz awk sudo dd; do
    command -v "$tool" >/dev/null || fail "필요한 명령이 없습니다: $tool"
done

[[ -b "$device" ]] || fail "블록 장치가 아닙니다: $device"
[[ $(lsblk -dnro TYPE -- "$device") == disk ]] || fail '파티션이 아닌 전체 디스크를 지정하세요.'
[[ $(lsblk -dnro RO -- "$device") == 0 ]] || fail '읽기 전용 장치입니다.'
[[ -r "$image" ]] || fail "이미지를 읽을 수 없습니다: $image"

check_unmounted() {
    local mounts
    mounts=$(lsblk -nrpo MOUNTPOINTS -- "$device")
    if [[ -n ${mounts//[[:space:]]/} ]]; then
        lsblk -o NAME,SIZE,TYPE,MOUNTPOINTS -- "$device"
        fail '사용 중인 파티션이 있습니다. SD카드의 마운트(또는 swap)를 모두 해제한 뒤 다시 실행하세요.'
    fi
    local types
    types=$(lsblk -nro TYPE -- "$device")
    while IFS= read -r type; do
        [[ $type == disk || $type == part ]] || fail '장치가 LVM/RAID/암호화 등 다른 블록 장치에서 사용 중입니다.'
    done <<< "$types"
}

check_unmounted
image_bytes=$(xz --robot --list -- "$image" | awk '$1 == "totals" {print $5}')
device_bytes=$(lsblk -bdnro SIZE -- "$device")
[[ $image_bytes =~ ^[0-9]+$ && $device_bytes =~ ^[0-9]+$ ]] || fail '이미지 또는 장치 크기를 확인할 수 없습니다.'
(( device_bytes >= image_bytes )) || fail 'SD카드 용량이 압축 해제된 이미지보다 작습니다.'

printf '\n이미지: %s\n기록 대상:\n' "$image"
lsblk -o NAME,SIZE,MODEL,TYPE,MOUNTPOINTS -- "$device"
printf '\n주의: %s의 모든 기존 데이터가 삭제됩니다.\n' "$device"

printf '\n압축 이미지 무결성을 확인합니다...\n'
xz --test -- "$image"
sudo -v
check_unmounted
printf 'SD카드에 기록합니다...\n'
xz -dc -- "$image" | sudo dd of="$device" bs=4M iflag=fullblock status=progress conv=fsync
printf '\n기록과 디스크 동기화가 완료되었습니다. SD카드를 분리해도 됩니다.\n'
