FILESEXTRAPATHS:prepend := "${THISDIR}/${PN}:"

SRC_URI:append = " \
    file://0001-init-report-kernel-total-time.patch \
    file://0002-init-import-u-boot-boot-metrics.patch \
    file://0003-timekeeping-report-gtc-monotonic-bridge.patch \
"
