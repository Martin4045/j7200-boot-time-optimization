FILESEXTRAPATHS:prepend := "${THISDIR}/${PN}:"

SRC_URI:append = " file://0001-j7200-skip-redundant-mmc-rescan.patch"
SRC_URI:append = " file://0002-j7200-silent-console-boot-metric.patch"
SRC_URI:append = " file://0003-j7200-default-loglevel-without-earlycon.patch"
SRC_URI:append = " file://fastboot.config"

UBOOT_CONFIG_FRAGMENTS = "fastboot.config"

do_configure:prepend() {
    install -m 0644 ${WORKDIR}/fastboot.config ${S}/configs/
}
