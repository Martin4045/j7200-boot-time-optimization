FILESEXTRAPATHS:prepend := "${THISDIR}/${PN}:"

SRC_URI:append = " \
    file://0001-init-report-kernel-total-time.patch \
    file://0002-init-import-u-boot-boot-metrics.patch \
    file://0003-timekeeping-report-gtc-monotonic-bridge.patch \
"

# Generate deterministic storage forms from the exact deployed raw ARM64
# Image. The kernel source, .config, DTBs and Image itself are unchanged.
do_deploy[depends]:append:j7200 = " lz4-native:do_populate_sysroot gzip-native:do_populate_sysroot"

do_deploy:append:j7200() {
    lz4 -q -f -9 \
        "${B}/${KERNEL_OUTPUT_DIR}/Image" \
        "${DEPLOYDIR}/Image.lz4"
    gzip -n -9 -c "${B}/${KERNEL_OUTPUT_DIR}/Image" \
        > "${DEPLOYDIR}/Image.gz"
}
