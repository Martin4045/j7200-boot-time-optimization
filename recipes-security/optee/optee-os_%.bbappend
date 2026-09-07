# Keep OP-TEE and error diagnostics while compiling out normal I/TC messages.
# OP-TEE TRACE_INFO is level 2; level 1 retains E/TC only.
EXTRA_OEMAKE:append:j7200 = " CFG_TEE_CORE_LOG_LEVEL=1"
