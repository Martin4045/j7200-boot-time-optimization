FILESEXTRAPATHS:prepend := "${THISDIR}/${PN}:"

SRC_URI:append:j7200 = " \
    file://0003-j7200-restore-hbmc-dll-calibration.patch \
    file://0004-j7200-default-to-emmc-uda.patch \
    file://0005-j7200-boot-kernel-from-hyperflash.patch \
"
