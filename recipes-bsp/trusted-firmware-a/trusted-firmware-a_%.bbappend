# Preserve TF-A functionality but compile out NOTICE/WARNING/INFO messages.
# LOG_LEVEL=10 retains ERROR output; BL31's normal banner is NOTICE (20).
EXTRA_OEMAKE:append:j7200 = " LOG_LEVEL=10"
