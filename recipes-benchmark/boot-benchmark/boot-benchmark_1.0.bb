SUMMARY = "Persistent multi-boot benchmark collector"
DESCRIPTION = "Collects kernel boot metrics and a configurable target timestamp across controlled reboot cycles"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = " \
    file://boot-benchmark \
    file://boot-benchmark-collector@.service \
"

S = "${WORKDIR}"

inherit systemd

SYSTEMD_SERVICE:${PN} = "boot-benchmark-collector@.service"
SYSTEMD_AUTO_ENABLE:${PN} = "disable"

RDEPENDS:${PN} += "systemd"

do_install() {
    install -d ${D}${sbindir}
    install -m 0755 ${WORKDIR}/boot-benchmark ${D}${sbindir}/boot-benchmark

    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/boot-benchmark-collector@.service \
        ${D}${systemd_system_unitdir}/boot-benchmark-collector@.service
}

FILES:${PN} += " \
    ${sbindir}/boot-benchmark \
    ${systemd_system_unitdir}/boot-benchmark-collector@.service \
"
