FILESEXTRAPATHS:prepend := "${THISDIR}/${PN}:"

SRC_URI:append:j7200 = " \
    file://0003-j7200-restore-hbmc-dll-calibration.patch \
    file://0006-j7200-boot-kernel-and-rootfs-from-network.patch \
"
