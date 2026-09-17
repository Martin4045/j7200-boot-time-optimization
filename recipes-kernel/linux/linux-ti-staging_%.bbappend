FILESEXTRAPATHS:prepend := "${THISDIR}/${PN}:"

SRC_URI:append = " \
    file://0001-init-report-kernel-total-time.patch \
    file://0002-init-import-u-boot-boot-metrics.patch \
    file://0003-timekeeping-report-gtc-monotonic-bridge.patch \
"

SRC_URI:append:j7200-evm = " file://0004-j7200-hyperflash-layout.patch"
SRC_URI:append:j7200-evm = " file://j7200-hyperflash.cfg"
KERNEL_CONFIG_FRAGMENTS:append:j7200-evm = " ${WORKDIR}/j7200-hyperflash.cfg"
