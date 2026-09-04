FILESEXTRAPATHS:prepend := "${THISDIR}/${PN}:"

SRC_URI:append = " file://0001-j7200-skip-redundant-mmc-rescan.patch"
SRC_URI:append = " file://0002-j7200-silent-console-boot-metric.patch"
SRC_URI:append = " file://0003-j7200-default-loglevel-without-earlycon.patch"
SRC_URI:append = " file://0004-add-optimized-boot-coarse-profiling.patch"
SRC_URI:append = " file://0005-profile-pre-board-init-f.patch"
SRC_URI:append = " file://fastboot.config"
SRC_URI:append = " file://sd-only.config"

UBOOT_CONFIG_FRAGMENTS = "fastboot.config sd-only.config"

do_configure:prepend() {
    install -m 0644 ${WORKDIR}/fastboot.config ${S}/configs/
    install -m 0644 ${WORKDIR}/sd-only.config ${S}/configs/
}
