FILESEXTRAPATHS:prepend := "${THISDIR}/${PN}:"

SRC_URI:append = " \
    file://0001-j7200-report-continuous-boot-wall-time.patch \
    file://0002-j7200-pass-boot-metrics-to-linux.patch \
    file://0003-j7200-skip-full-u-boot-board-late-detection.patch \
    file://0004-j7200-r5-select-required-elf-library.patch \
    file://0005-j7200-use-minimal-a72-environment.patch \
    file://0006-j7200-print-final-metric-with-silent-console.patch \
    file://0007-j7200-suppress-normal-silent-boot-messages.patch \
    file://j7200-a72-minimal.config;subdir=git/configs \
    file://j7200-r5-minimal.config;subdir=git/configs \
"

# Keep the A72 and R5 experiments strictly separate.  j7200-evm is also a
# MACHINEOVERRIDE of j7200-evm-k3r5, so override syntax alone would apply the
# A72 fragment to the R5 build as well.  Select by the exact MACHINE instead.
UBOOT_CONFIG_FRAGMENTS:append = " ${@'j7200-r5-minimal.config' if d.getVar('MACHINE') == 'j7200-evm-k3r5' else 'j7200-a72-minimal.config' if d.getVar('MACHINE') == 'j7200-evm' else ''}"

# HyperFlash fragments override SD-only choices; the DMA fragment is A72-only.
SRC_URI:append = " \
    file://0008-j7200-hyperflash-boot-and-metrics.patch \
    file://0009-j7200-hyperflash-dma.config.patch \
    file://j7200-hyperflash.config;subdir=git/configs \
    file://j7200-a72-hyperflash.config;subdir=git/configs \
"
UBOOT_CONFIG_FRAGMENTS:append = " ${@'j7200-hyperflash.config j7200-a72-hyperflash.config j7200-a72-hyperflash-dma.config' if d.getVar('MACHINE') == 'j7200-evm' else 'j7200-hyperflash.config' if d.getVar('MACHINE') == 'j7200-evm-k3r5' else ''}"

do_configure[depends] += "${@'virtual/kernel:do_deploy' if d.getVar('MACHINE') == 'j7200-evm' else ''}"
do_configure[prefuncs] += "hyperflash_boot_lengths"

python hyperflash_boot_lengths() {
    import os
    if d.getVar('MACHINE') != 'j7200-evm':
        return
    deploy = d.getVar('DEPLOY_DIR_IMAGE')
    values = {}
    for token, name, limit in [('@KERNEL_SIZE@', 'Image', 0x3800000),
                               ('@DTB_SIZE@', 'k3-j7200-common-proc-board.dtb', 0x100000)]:
        size = os.path.getsize(os.path.join(deploy, name))
        if not 0 < size <= limit:
            bb.fatal('HyperFlash %s size 0x%x exceeds slot 0x%x' % (name, size, limit))
        values[token] = '0x%x' % size
    # Read the unmodified WORKDIR template so repeated configure is safe.
    import bb.fetch2
    fetch = bb.fetch2.Fetch(d.getVar('SRC_URI').split(), d)
    template = fetch.localpath('file://j7200-a72-hyperflash.config;subdir=git/configs')
    with open(template) as f:
        config = f.read()
    for token, value in values.items():
        config = config.replace(token, value)
    with open(os.path.join(d.getVar('S'), 'configs/j7200-a72-hyperflash.config'), 'w') as f:
        f.write(config)
}
