FILESEXTRAPATHS:prepend := "${THISDIR}/${PN}:"

SRC_URI:append = " \
    file://0001-init-report-kernel-total-time.patch \
    file://console-loglevel.cfg \
"

KERNEL_CONFIG_FRAGMENTS:append = " ${WORKDIR}/console-loglevel.cfg"
