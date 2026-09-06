*** Variables ***
# Connection profile. Real hardware is disabled until HIL_ENABLE is explicitly true.
${HIL_ENABLE}                  ${TRUE}
${CONNECTION_TYPE}             usb
${N6775A_USB_RESOURCE}          USB0::0x0957::0x0907::MY43014421::INSTR
${N6700_RESOURCE}              ${N6775A_USB_RESOURCE}
${N6700_PORT}                  5025
${N6700_ALIAS}                 n6775a_self_check
${CHANNEL}                     1
${EXPECTED_MODULE}             N6775A

# Destructive or energizing operations are separately guarded.
${ALLOW_RESET}                 ${TRUE}
${ALLOW_ACTIVE_OUTPUT}         ${TRUE}

# N6775A published ratings: 60 V, 5 A, 300 W. Defaults remain deliberately low.
${MODULE_MAX_VOLTAGE}          60.0
${MODULE_MAX_CURRENT}          5.0
${MODULE_MAX_POWER}            300.0
${TEST_VOLTAGE}                1.0
${TEST_CURRENT_LIMIT}          0.10
${TEST_OVP}                    2.0
${ACTIVE_VOLTAGE_MIN}          0.75
${ACTIVE_VOLTAGE_MAX}          1.25
${ACTIVE_TIMEOUT}              10s
${READBACK_TOLERANCE}          0.01
${MEASUREMENT_TOLERANCE}       0.25

# RFDS-019 protocol evidence is written into the Robot output directory.
${PROTOCOL_TRACE}              ${OUTPUT DIR}${/}protocol_trace.jsonl
${ENVIRONMENT_EVIDENCE}        ${OUTPUT DIR}${/}environment.json
${DEVICE_EVIDENCE}             ${OUTPUT DIR}${/}device_identity.json

# Initialized fallbacks keep teardown safe when setup fails before state capture.
${ORIGINAL_OUTPUT}              ${FALSE}
${ORIGINAL_VOLTAGE}             0.0
${ORIGINAL_CURRENT}             0.1
${ORIGINAL_OVP}                 60.0
${ORIGINAL_OCP}                 ${FALSE}
