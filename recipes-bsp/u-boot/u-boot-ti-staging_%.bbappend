FILESEXTRAPATHS:prepend := "${THISDIR}/${PN}:"

SRC_URI:append = " \
    file://0001-j7200-report-continuous-boot-wall-time.patch \
    file://0002-j7200-pass-boot-metrics-to-linux.patch \
    file://0003-j7200-skip-full-u-boot-board-late-detection.patch \
    file://0004-j7200-r5-select-required-elf-library.patch \
    file://0005-j7200-use-minimal-a72-environment.patch \
    file://0006-j7200-print-final-metric-with-silent-console.patch \
    file://0007-j7200-suppress-normal-silent-boot-messages.patch \
    file://0008-j7200-a72-spl-trace-mmc-payload-load.patch \
    file://0009-j7200-trace-spl-to-full-uboot-handoff.patch \
    file://0010-j7200-trace-direct-sd-boot-command.patch \
    file://j7200-a72-minimal.config;subdir=git/configs \
    file://j7200-r5-minimal.config;subdir=git/configs \
"

# Keep the A72 and R5 experiments strictly separate.  j7200-evm is also a
# MACHINEOVERRIDE of j7200-evm-k3r5, so override syntax alone would apply the
# A72 fragment to the R5 build as well.  Select by the exact MACHINE instead.
UBOOT_CONFIG_FRAGMENTS:append = " ${@'j7200-r5-minimal.config' if d.getVar('MACHINE') == 'j7200-evm-k3r5' else 'j7200-a72-minimal.config' if d.getVar('MACHINE') == 'j7200-evm' else ''}"
