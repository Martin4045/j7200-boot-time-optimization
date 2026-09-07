FILESEXTRAPATHS:prepend := "${THISDIR}/${PN}:"

SRC_URI:append = " \
    file://0001-j7200-report-continuous-boot-wall-time.patch \
    file://0002-j7200-pass-boot-metrics-to-linux.patch \
"
