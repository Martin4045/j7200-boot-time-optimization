# Retain error diagnostics without boot-time NOTICE tracing.
EXTRA_OEMAKE:append:j7200 = " LOG_LEVEL=10"

# Falcon BL33 is Linux; x0 is its device tree.
EXTRA_OEMAKE:append:j7200 = " PRELOADED_BL33_BASE=0x82000000 K3_HW_CONFIG_BASE=0x88000000"

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI:append:j7200 = " file://0001-j7200-falcon-core1-cleanup.patch"
EXTRA_OEMAKE:append:j7200 = " J7200_FALCON_CORE1_CLEANUP=1"
