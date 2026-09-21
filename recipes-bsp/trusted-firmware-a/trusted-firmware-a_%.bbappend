# Preserve TF-A functionality but compile out NOTICE/WARNING/INFO messages.
# LOG_LEVEL=10 retains ERROR output; BL31's normal banner is NOTICE (20).
EXTRA_OEMAKE:append:j7200 = " LOG_LEVEL=10"

# Falcon BL33 is Linux; x0 is its device tree.
EXTRA_OEMAKE:append:j7200 = " PRELOADED_BL33_BASE=0x82000000 K3_HW_CONFIG_BASE=0x88000000"
