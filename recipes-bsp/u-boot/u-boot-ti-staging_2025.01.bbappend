FILESEXTRAPATHS:prepend := "${THISDIR}/${PN}:"

SRC_URI:append:j7200 = " \
    file://0003-j7200-restore-hbmc-dll-calibration.patch \
"
