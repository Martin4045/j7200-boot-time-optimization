#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
action=${1:-check}
config=${2:-"$script_dir/nfs-boot-static.conf"}

fail() {
    printf '오류: %s\n' "$*" >&2
    exit 1
}

usage() {
    printf '사용법: %s {check|apply} [설정파일]\n' "$0"
}

[[ -r $config ]] || fail "설정 파일을 읽을 수 없습니다: $config"
# shellcheck source=nfs-boot-static.conf
source "$config"

required_vars=(
    PC_INTERFACE PC_CONNECTION PC_IP BOARD_IP PREFIX_LENGTH NETMASK
    NFS_EXPORT_NETWORK TFTP_ROOT NFS_ROOT DEPLOY_DIR
)
for var in "${required_vars[@]}"; do
    [[ -n ${!var:-} ]] || fail "설정값이 비어 있습니다: $var"
done

kernel="$DEPLOY_DIR/Image"
dtb="$DEPLOY_DIR/k3-j7200-common-proc-board.dtb"
rootfs="$DEPLOY_DIR/tisdk-default-image-j7200-evm.rootfs.tar.xz"
initial_env="$DEPLOY_DIR/u-boot-ti-staging-initial-env-j7200-evm"
export_line="$NFS_ROOT $NFS_EXPORT_NETWORK(rw,sync,no_subtree_check,no_root_squash)"

check_files() {
    [[ -s $kernel ]] || fail "Kernel이 없습니다: $kernel"
    [[ -s $dtb ]] || fail "DTB가 없습니다: $dtb"
    [[ -s $rootfs ]] || fail "rootfs archive가 없습니다: $rootfs"
    [[ -s $initial_env ]] || fail "U-Boot initial environment가 없습니다: $initial_env"
    grep -Fxq "ipaddr=$BOARD_IP" "$initial_env" ||
        fail "U-Boot의 보드 IP가 설정 파일과 다릅니다: $BOARD_IP"
    grep -Fxq "serverip=$PC_IP" "$initial_env" ||
        fail "U-Boot의 서버 IP가 설정 파일과 다릅니다: $PC_IP"
    grep -Fxq "netmask=$NETMASK" "$initial_env" ||
        fail "U-Boot의 netmask가 설정 파일과 다릅니다: $NETMASK"
}

show_status() {
    printf 'PC interface : %s\n' "$PC_INTERFACE"
    printf 'PC address   : %s/%s\n' "$PC_IP" "$PREFIX_LENGTH"
    printf 'Board address: %s/%s\n' "$BOARD_IP" "$PREFIX_LENGTH"
    printf 'TFTP root    : %s\n' "$TFTP_ROOT"
    printf 'NFS root     : %s\n' "$NFS_ROOT"
    ip -4 -brief address show dev "$PC_INTERFACE" 2>/dev/null || true
    nmcli -t -f DEVICE,STATE,CONNECTION device status 2>/dev/null |
        awk -F: -v dev="$PC_INTERFACE" '$1 == dev' || true
    systemctl is-active tftpd-hpa nfs-kernel-server 2>/dev/null || true
}

case "$action" in
    check)
        check_files
        show_status
        ;;
    apply)
        check_files
        for tool in nmcli sudo install tar grep systemctl; do
            command -v "$tool" >/dev/null || fail "필요한 명령이 없습니다: $tool"
        done
        sudo -v

        if nmcli -t -f NAME connection show | grep -Fxq "$PC_CONNECTION"; then
            sudo nmcli connection modify "$PC_CONNECTION" \
                connection.interface-name "$PC_INTERFACE" \
                connection.autoconnect yes \
                ipv4.method manual \
                ipv4.addresses "$PC_IP/$PREFIX_LENGTH" \
                ipv4.gateway "" \
                ipv4.dns "" \
                ipv4.never-default yes \
                ipv6.method disabled \
                802-3-ethernet.auto-negotiate yes
        else
            sudo nmcli connection add type ethernet \
                ifname "$PC_INTERFACE" \
                con-name "$PC_CONNECTION" \
                ipv4.method manual \
                ipv4.addresses "$PC_IP/$PREFIX_LENGTH" \
                ipv4.never-default yes \
                ipv6.method disabled \
                802-3-ethernet.auto-negotiate yes
        fi
        sudo nmcli connection up "$PC_CONNECTION"

        sudo install -d "$TFTP_ROOT" "$NFS_ROOT"
        sudo install -m 0644 "$kernel" "$TFTP_ROOT/Image"
        sudo install -m 0644 "$dtb" \
            "$TFTP_ROOT/k3-j7200-common-proc-board.dtb"

        if [[ ! -e $NFS_ROOT/sbin/init && ! -e $NFS_ROOT/usr/lib/systemd/systemd ]]; then
            sudo tar --numeric-owner -xJpf "$rootfs" -C "$NFS_ROOT"
        else
            printf '기존 NFS rootfs를 유지합니다: %s\n' "$NFS_ROOT"
        fi

        if ! grep -Fqx "$export_line" /etc/exports; then
            printf '%s\n' "$export_line" | sudo tee -a /etc/exports >/dev/null
        fi
        sudo exportfs -rav
        sudo systemctl restart tftpd-hpa nfs-kernel-server
        show_status
        printf '고정 IP TFTP/NFS 서버 설정이 완료되었습니다. DHCP는 사용하지 않습니다.\n'
        ;;
    *)
        usage >&2
        exit 1
        ;;
esac
