SUMMARY = "External-data Falcon FIT using verified eMMC Conventional payloads"
LICENSE = "CLOSED"
COMPATIBLE_MACHINE = "^j7200-evm$"
PACKAGE_ARCH = "${MACHINE_ARCH}"
inherit deploy
DEPENDS = "u-boot-tools-native dtc-native"
EMMC_FALCON_BASELINE_DIR ?= ""
FILESEXTRAPATHS:prepend := "${EMMC_FALCON_BASELINE_DIR}:"
SRC_URI = "file://fitImage.its file://Image file://k3-j7200-common-proc-board.dtb"
S = "${WORKDIR}"
B = "${WORKDIR}/build"
do_configure[noexec] = "1"
python do_compile() {
    import hashlib, pathlib, shutil, subprocess, struct
    source = pathlib.Path(d.getVar('WORKDIR'))
    build = pathlib.Path(d.getVar('B'))
    build.mkdir(exist_ok=True)
    expected = {
        'Image': 'b00eec5992625794b4bc7f68b89f1fdfeb038fa4249a4d94738bff65ddeed0cb',
        'k3-j7200-common-proc-board.dtb': '9d46be45371e4919f5136c6e7741ff74ae5fa615c34b644b761c759663e78539',
    }
    for name, digest in expected.items():
        payload = (source / name).read_bytes()
        if hashlib.sha256(payload).hexdigest() != digest:
            bb.fatal('Conventional payload hash mismatch: ' + name)
        shutil.copyfile(source / name, build / name)
    kernel = (build / 'Image').read_bytes()
    runtime_size = struct.unpack_from('<Q', kernel, 16)[0]
    if not runtime_size or max(len(kernel), runtime_size) > 0x05f00000:
        bb.fatal('Kernel overlaps the R5 stack guard below 0x88000000')
    shutil.copyfile(source / 'fitImage.its', build / 'fitImage.its')
    subprocess.check_call(['mkimage', '-E', '-B', '0x200', '-f', 'fitImage.its', 'fitImage'], cwd=build)
    fit = (build / 'fitImage').read_bytes()
    if struct.unpack_from('>I', fit, 4)[0] > 0x10000:
        bb.fatal('External FIT metadata exceeds 64 KiB budget')
}
do_install[noexec] = "1"
do_deploy() {
    install -m 0644 ${B}/fitImage ${DEPLOYDIR}/fitImage
}
addtask deploy after do_compile before do_build
