"""Generate and verify RFDS-017/RFDS-018 AI contracts for this driver.

The generated ``*.yaml`` files intentionally use JSON-compatible YAML 1.2. This
keeps generation deterministic and lets the package verifier validate them using
only the Python standard library.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT_NAME = "rf_keysight_n6700"
LIBRARY_SOURCE = Path("KeysightN6700Library/library.py")
AI_CONTRACT = Path("ai/keysight_n6700_ai_contract.yaml")
AI_LOCK = Path("ai/keysight_n6700_ai_contract.lock")
SYSTEM_CONTRACT = Path("system_ai_contract.yaml")
N6775A_USB_RESOURCE = "USB0::0x0957::0x0907::MY43014421::INSTR"
VERSION_RE = re.compile(r'^version\s*=\s*"(?P<version>\d+\.\d+\.\d+)"\s*$', re.MULTILINE)


@dataclass(frozen=True)
class ArgumentSpec:
    name: str
    type: str
    required: bool
    default: Any


@dataclass(frozen=True)
class KeywordSpec:
    robot_keyword: str
    python_method: str
    signature: str
    arguments: tuple[ArgumentSpec, ...]
    return_type: str
    purpose: str
    documentation: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def parse_version(repo: Path) -> str:
    text = (repo / "pyproject.toml").read_text(encoding="utf-8")
    match = VERSION_RE.search(text)
    if match is None:
        raise ValueError("Could not find project version in pyproject.toml")
    return match.group("version")


def release_from_version(version: str) -> str:
    year, release, _patch = version.split(".")
    return f"{int(year):02d}.{int(release):02d}"


def literal_default(node: ast.expr | None) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return ast.unparse(node)


def parse_keywords(source: str) -> list[KeywordSpec]:
    module = ast.parse(source)
    library_class = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == "KeysightN6700Library"
    )
    result: list[KeywordSpec] = []
    for node in library_class.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        robot_name: str | None = None
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Name)
                and decorator.func.id == "keyword"
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
                and isinstance(decorator.args[0].value, str)
            ):
                robot_name = decorator.args[0].value
                break
        if robot_name is None:
            continue

        positional = node.args.posonlyargs + node.args.args
        defaults: list[ast.expr | None] = [None] * (len(positional) - len(node.args.defaults)) + list(
            node.args.defaults
        )
        arguments: list[ArgumentSpec] = []
        signature_parts: list[str] = []
        for argument, default_node in zip(positional, defaults, strict=True):
            if argument.arg == "self":
                continue
            annotation = ast.unparse(argument.annotation) if argument.annotation is not None else "Any"
            required = default_node is None
            default = literal_default(default_node)
            arguments.append(ArgumentSpec(argument.arg, annotation, required, default))
            signature_part = f"{argument.arg}: {annotation}"
            if not required:
                signature_part += f" = {ast.unparse(default_node)}"
            signature_parts.append(signature_part)
        return_type = ast.unparse(node.returns) if node.returns is not None else "Any"
        documentation = ast.get_docstring(node) or ""
        purpose = documentation.splitlines()[0].strip() if documentation else robot_name
        result.append(
            KeywordSpec(
                robot_keyword=robot_name,
                python_method=node.name,
                signature=f"{robot_name}({', '.join(signature_parts)}) -> {return_type}",
                arguments=tuple(arguments),
                return_type=return_type,
                purpose=purpose,
                documentation=documentation,
            )
        )
    return result


INPUT_DESCRIPTIONS: dict[str, str] = {
    "resource": "VISA resource string, hostname, IP address, or empty value for simulator/discovery according to connection_type.",
    "host": "Instrument hostname or IPv4/IPv6 address.",
    "port": "Raw SCPI TCP port; 5025 is the normal N6700 socket port.",
    "alias": "Named session. Omit to use the currently selected session where allowed.",
    "connection_type": "One of visa, usb, ethernet, socket, or simulated.",
    "discover": "Allow driver discovery when the selected transport supports it.",
    "reset_on_connect": "Explicitly reset the instrument after opening. Unsafe for unknown live setups.",
    "clear_errors_on_connect": "Explicitly drain/clear stale instrument errors after opening.",
    "audit_log_path": "Optional path for command/response audit logging.",
    "replace": "Permit replacement of an existing session with the same alias.",
    "command": "SCPI command or query. Raw commands bypass typed capability and safety checks.",
    "check_errors": "Override post-write SCPI error checking for this raw command.",
    "channel": "Mainframe channel number, 1 through 4; installed module capability must match the operation.",
    "channels": "Unique channel list or comma/space separated string; 'all' selects channels 1 through 4.",
    "voltage": "Voltage in volts; engineering forms such as 12V and 50mV are accepted.",
    "voltage_range": "Optional instrument voltage range in volts.",
    "current": "Current in amperes; engineering forms such as 500mA are accepted.",
    "current_range": "Optional instrument current range in amperes.",
    "current_limit": "Current limit in amperes.",
    "voltage_limit": "Voltage compliance/limit in volts.",
    "output": "Whether the source output is enabled after configuration; safe default is false.",
    "enabled": "Requested boolean state.",
    "ovp": "Optional over-voltage protection threshold in volts.",
    "ocp": "Optional over-current protection enable state.",
    "expected": "Expected measured value or state.",
    "tolerance": "Absolute allowed deviation, using the same physical unit as expected.",
    "minimum": "Inclusive minimum acceptable voltage.",
    "maximum": "Inclusive maximum acceptable voltage.",
    "timeout": "Maximum wait duration, supporting ms, s, and min suffixes.",
    "poll_interval": "Delay between voltage polls.",
    "restore_output": "Restore the pre-clear output state after clearing protection. Safe default is false.",
    "force_output_off_first": "Disable the channel before clearing protection. Safe default is true.",
    "verify_cleared": "Read protection state after clear and fail if the fault remains.",
    "mode": "Operation mode accepted by the keyword, as documented in purpose/constraints.",
    "value": "Mode-dependent load level in A, V, ohm, or W.",
    "input_on": "Whether the load input is enabled after configuration; safe default is false.",
}


def normalized_id(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def category(keyword: KeywordSpec) -> str:
    name = keyword.robot_keyword
    if name.startswith("Connect") or name.startswith("Disconnect") or name.startswith("Select") or "Alias" in name:
        return "session_management"
    if "SCPI" in name or "Status" in name or "Errors" in name or "Self Test" in name or name.startswith("Reset"):
        return "instrument_control"
    if "Protection" in name or "Over Voltage" in name or "Over Current" in name or "Shutdown" in name:
        return "safety_and_protection"
    if "Measure" in name or "Should Be" in name or name.startswith("Wait Until"):
        return "measurement_and_verification"
    if "SMU" in name:
        return "smu"
    if "Load" in name:
        return "electronic_load"
    if "Output" in name or "Voltage" in name or "Current" in name or "Power Supply" in name:
        return "power_supply"
    return "discovery"


def is_read_only(keyword: KeywordSpec) -> bool:
    name = keyword.robot_keyword
    prefixes = ("Get ", "Discover ", "Query ", "Measure ", "N6700 ", "Wait Until ", "Run N6700 Self Test", "Check N6700")
    return name.startswith(prefixes) or name in {
        "Get Current N6700 Alias",
        "Get Connected N6700 Aliases",
    }


def may_energize(keyword: KeywordSpec) -> bool:
    return keyword.robot_keyword in {
        "Set N6700 Output",
        "Turn On N6700 Output",
        "Set N6700 Outputs",
        "Configure N6700 Power Supply Channel",
        "Configure N6700 SMU Voltage Priority",
        "Configure N6700 SMU Current Priority",
        "Clear N6700 Protection",
        "Set N6700 Load Input",
        "Turn On N6700 Load Input",
        "Configure N6700 Load CC",
        "Write N6700 SCPI",
        "Reset N6700",
    }


def risk_level(keyword: KeywordSpec) -> str:
    name = keyword.robot_keyword
    if name == "Write N6700 SCPI":
        return "critical"
    if may_energize(keyword):
        return "high"
    if name.startswith("Set ") or name.startswith("Configure ") or name in {
        "Clear N6700 Status",
        "Drain N6700 Errors",
    }:
        return "medium"
    if name.startswith("Disconnect") or name.startswith("Shutdown") or name.startswith("Turn Off"):
        return "low"
    return "low"


def module_requirement(keyword: KeywordSpec) -> str | None:
    name = keyword.robot_keyword
    if "Load" in name:
        return "electronic_load"
    if "SMU" in name:
        return "smu"
    if any(token in name for token in ("Voltage", "Current", "Power Supply", "Output")) and "Measure" not in name and "Should" not in name and "Wait" not in name:
        return "source_or_smu"
    if "Measure" in name or "Should Be" in name or "Protection" in name:
        return "installed_module_supporting_requested_quantity"
    return None


def preconditions(keyword: KeywordSpec) -> list[str]:
    name = keyword.robot_keyword
    result: list[str] = []
    if name.startswith("Connect"):
        result.append("Requested transport dependency is installed and the resource is reachable, unless simulated mode is selected.")
        result.append("Alias replacement is explicit when an alias already exists.")
    elif name in {"Get Current N6700 Alias", "Get Connected N6700 Aliases", "Disconnect All N6700"}:
        pass
    else:
        result.append("A named N6700 session is connected; alias exists or a current alias is selected.")
    if any(arg.name == "channel" for arg in keyword.arguments):
        result.append("Channel is in range 1..4 and an installed module is present.")
    required_module = module_requirement(keyword)
    if required_module:
        result.append(f"Channel capability is compatible with {required_module} operation; confirm with Discover N6700 Modules.")
    if may_energize(keyword):
        result.append("Wiring, DUT limits, protection thresholds, and operator authorization have been verified before any energizing option is used.")
    if name == "Write N6700 SCPI":
        result.append("The exact raw SCPI command has been reviewed against the installed model/module programming guide.")
    if name.startswith("N6700 ") and "Should Be" in name or name.startswith("Wait Until"):
        result.append("Expected values and tolerances originate from an approved requirement or calibrated reference.")
    return result or ["No active instrument session is required."]


def postconditions(keyword: KeywordSpec) -> list[str]:
    name = keyword.robot_keyword
    if name.startswith("Connect"):
        return ["Session alias is registered and selected.", "Instrument identity has been queried successfully."]
    if name.startswith("Disconnect"):
        return ["Requested session(s) are closed.", "When auto_shutdown is enabled, controllable outputs/load inputs were commanded off before close on a best-effort basis."]
    if name == "Select N6700":
        return ["Selected alias becomes the default session for following keywords."]
    if name.startswith(("Get ", "Discover ", "Query ", "Measure ", "Run ", "Check ", "N6700 ", "Wait Until ")):
        return ["Requested information or verification result is returned.", "No intentional output configuration change is made, except instrument-internal effects of self-test or error-queue reads."]
    if name.startswith("Turn Off") or name.startswith("Shutdown"):
        return ["Target output/load input is disabled or a detailed failure result is returned."]
    if name == "Clear N6700 Protection":
        return ["Protection clear was attempted with output off first by default.", "Output remains off unless restore_output was explicitly true."]
    if name.startswith("Set ") or name.startswith("Configure ") or name.startswith("Turn On"):
        return ["Requested instrument state is programmed.", "With strict_errors enabled, the SCPI error queue is checked after typed mutation."]
    if name == "Reset N6700":
        return ["Instrument reset command completed; all prior assumptions about configuration must be re-established."]
    return ["Keyword completes or raises a categorized error."]


def side_effects(keyword: KeywordSpec) -> list[str]:
    name = keyword.robot_keyword
    effects: list[str] = []
    if name.startswith("Connect"):
        effects.extend(["Opens VISA or TCP resources.", "Queries instrument identity.", "May create an audit log file."])
    elif name.startswith("Disconnect"):
        effects.extend(["May command all outputs/load inputs off.", "Closes transport resources."])
    elif name == "Select N6700":
        effects.append("Changes the library's current session alias.")
    elif name == "Write N6700 SCPI":
        effects.append("Arbitrary instrument state change is possible, including energization, trigger, memory, and protection changes.")
    elif name == "Reset N6700":
        effects.append("Resets instrument configuration and may interrupt active tests.")
    elif name.startswith(("Set ", "Configure ", "Turn On", "Turn Off", "Clear ", "Shutdown")):
        effects.append("Changes instrument or channel state.")
    elif name in {"Drain N6700 Errors", "Check N6700 Errors"}:
        effects.append("Consumes entries from the SCPI error queue.")
    elif name == "Run N6700 Self Test":
        effects.append("Instrument may be temporarily unavailable while self-test executes.")
    else:
        effects.append("Performs query/measurement traffic only.")
    return effects


def timing(keyword: KeywordSpec) -> dict[str, Any]:
    name = keyword.robot_keyword
    nominal = 250
    maximum = 5000
    timeout_parameter: str | None = None
    if name.startswith("Connect"):
        nominal, maximum = 1500, 15000
    elif name == "Run N6700 Self Test":
        nominal, maximum = 10000, 120000
    elif name == "Reset N6700":
        nominal, maximum = 3000, 30000
    elif name.startswith("Measure") or "Should Be" in name:
        nominal, maximum = 500, 10000
    elif name.startswith("Wait Until"):
        nominal, maximum, timeout_parameter = 0, None, "timeout"
    stabilization = {
        "minimum_seconds": 0.0,
        "recommended_seconds": 0.0,
        "source": "driver",
    }
    if may_energize(keyword):
        stabilization = {
            "minimum_seconds": 0.0,
            "recommended_seconds": "UNKNOWN",
            "source": "DUT/test-plan requirement",
            "planning_rule": "Do not measure immediately after energization unless the approved requirement explicitly permits it.",
        }
    return {
        "nominal_milliseconds": nominal,
        "maximum_milliseconds": maximum,
        "timeout_parameter": timeout_parameter,
        "stabilization_delay": stabilization,
    }


def retry_policy(keyword: KeywordSpec) -> dict[str, Any]:
    if is_read_only(keyword):
        return {
            "automatic_retry": False,
            "maximum_attempts": 2,
            "allowed_only_for": ["N6700TimeoutError", "N6700CommunicationError"],
            "rule": "Retry once only after confirming the session is still valid and no state-changing command is pending.",
        }
    return {
        "automatic_retry": False,
        "maximum_attempts": 1,
        "allowed_only_for": [],
        "rule": "Do not retry a state-changing keyword blindly. Query actual state, make the bench safe, then decide explicitly.",
    }


def exclusive_resources(keyword: KeywordSpec) -> list[str]:
    name = keyword.robot_keyword
    resources: list[str] = []
    if name.startswith("Connect"):
        resources.append("transport_resource(resource/host, port)")
        resources.append("session_alias(alias)")
    elif name not in {"Get Current N6700 Alias", "Get Connected N6700 Aliases"}:
        resources.append("n6700_session(alias_or_current)")
    if any(arg.name == "channel" for arg in keyword.arguments):
        resources.append("n6700_channel(alias_or_current, channel)")
    if any(arg.name == "channels" for arg in keyword.arguments) or name in {"Shutdown All N6700 Channels", "Reset N6700"}:
        resources.append("n6700_all_channels(alias_or_current)")
    if name == "Write N6700 SCPI":
        resources.append("n6700_entire_instrument(alias_or_current)")
    return resources


def input_contract(argument: ArgumentSpec) -> dict[str, Any]:
    value: dict[str, Any] = {
        "name": argument.name,
        "type": argument.type,
        "required": argument.required,
        "description": INPUT_DESCRIPTIONS.get(argument.name, f"Input argument {argument.name}."),
    }
    if not argument.required:
        value["default"] = argument.default
    return value


def output_contract(keyword: KeywordSpec) -> dict[str, Any]:
    if keyword.return_type == "None":
        return {"type": "None", "description": "No value; success is represented by keyword completion."}
    return {
        "type": keyword.return_type,
        "description": f"Robot-compatible result from {keyword.robot_keyword}. Dictionaries/lists contain Python primitives.",
    }


def errors_for(keyword: KeywordSpec) -> list[str]:
    result = ["ValueError", "RuntimeError"]
    if keyword.robot_keyword not in {"Get Current N6700 Alias", "Get Connected N6700 Aliases"}:
        result.extend(
            [
                "N6700ConnectionError",
                "N6700TimeoutError",
                "N6700CommunicationError",
                "N6700CommandError",
                "UnsupportedFeatureError",
                "InvalidChannelError",
                "SafetyInterlockError",
            ]
        )
    if "Protection" in keyword.robot_keyword or may_energize(keyword):
        result.append("N6700ProtectionError")
    return sorted(set(result))


def safe_default(keyword: KeywordSpec) -> str:
    name = keyword.robot_keyword
    if name in {"Configure N6700 Power Supply Channel", "Configure N6700 SMU Voltage Priority", "Configure N6700 SMU Current Priority"}:
        return "Output defaults off."
    if name == "Configure N6700 Load CC":
        return "Load input defaults off."
    if name == "Clear N6700 Protection":
        return "Output is forced off first and is not restored by default."
    if name.startswith("Disconnect"):
        return "auto_shutdown defaults true."
    if name.startswith("Connect"):
        return "Connection is non-invasive: no reset and no error clearing by default."
    return "No additional safe-default parameter beyond the typed keyword behavior."


def capability(keyword: KeywordSpec) -> dict[str, Any]:
    return {
        "id": normalized_id(keyword.robot_keyword),
        "robot_keyword": keyword.robot_keyword,
        "python_method": keyword.python_method,
        "category": category(keyword),
        "signature": keyword.signature,
        "purpose": keyword.purpose,
        "inputs": [input_contract(argument) for argument in keyword.arguments],
        "outputs": output_contract(keyword),
        "preconditions": preconditions(keyword),
        "postconditions": postconditions(keyword),
        "side_effects": side_effects(keyword),
        "risk_level": risk_level(keyword),
        "timing": timing(keyword),
        "retry_policy": retry_policy(keyword),
        "errors": errors_for(keyword),
        "exclusive_resources": exclusive_resources(keyword),
        "module_requirement": module_requirement(keyword) or "none",
        "mutating": not is_read_only(keyword),
        "may_energize_or_sink_power": may_energize(keyword),
        "safe_default": safe_default(keyword),
        "documentation": keyword.documentation,
    }


def build_ai_contract(version: str, release: str, keywords: list[KeywordSpec]) -> dict[str, Any]:
    return {
        "contract_standard": {"id": "RFDS-017", "version": "3.0", "status": "draft-source-conformant"},
        "contract_version": "1.0",
        "identity": {
            "driver_id": "keysight_n6700",
            "driver_name": "Keysight N6700 Robot Framework Driver",
            "release": release,
            "python_distribution": "robotframework-keysight-n6700",
            "python_version": version,
            "archive": f"rf_keysight_n6700_v{release}.zip",
            "internal_root": ROOT_NAME,
            "robot_library_import": "KeysightN6700Library",
            "robot_library_class": "KeysightN6700Library.KeysightN6700Library",
            "library_scope": "SUITE",
            "supported_family": "Keysight/Agilent N6700-series modular power systems",
            "channel_address_space": [1, 2, 3, 4],
            "authoritative_keyword_source": LIBRARY_SOURCE.as_posix(),
        },
        "mental_model": {
            "summary": "One N6700 mainframe session exposes up to four independently addressed module channels. Installed modules determine whether a channel acts as a power source, SMU, measurement source, or verified electronic load.",
            "session_model": "Multiple named sessions may exist; one alias is current. Most keywords accept an optional alias override.",
            "state_ownership": "The library tracks sessions and aliases, while the instrument is the authority for channel configuration, output state, protection state, and measurements.",
            "safety_model": "Typed configuration defaults outputs/load inputs off. Suite teardown and disconnect attempt shutdown when auto_shutdown is true. Raw SCPI bypasses typed safeguards.",
        },
        "state_machine": {
            "initial_state": "DISCONNECTED",
            "states": {
                "DISCONNECTED": "No transport resource is open.",
                "CONNECTED_SAFE_UNKNOWN": "Session open; identity known; channel states must be queried before assuming safety.",
                "CONFIGURED_OUTPUT_OFF": "Setpoints/protection configured and output/load input confirmed off.",
                "ENERGIZED_OR_SINKING": "At least one source output or load input is on.",
                "PROTECTION_TRIPPED": "Channel protection indicates a trip or interlock.",
                "FAULTED": "Communication, SCPI, verification, or shutdown failure requires operator review.",
            },
            "transitions": [
                {"from": "DISCONNECTED", "to": "CONNECTED_SAFE_UNKNOWN", "keywords": ["Connect To N6700", "Connect To Simulated N6700", "Connect To N6700 Via VISA", "Connect To N6700 Via Ethernet"]},
                {"from": "CONNECTED_SAFE_UNKNOWN", "to": "CONFIGURED_OUTPUT_OFF", "rule": "Discover modules, query state, configure limits with outputs off."},
                {"from": "CONFIGURED_OUTPUT_OFF", "to": "ENERGIZED_OR_SINKING", "rule": "Explicit output/load-input enable only after approved preconditions."},
                {"from": "ENERGIZED_OR_SINKING", "to": "CONFIGURED_OUTPUT_OFF", "rule": "Turn off target channel(s) and verify state."},
                {"from": "ANY_CONNECTED", "to": "PROTECTION_TRIPPED", "rule": "Protection/interlock reports active fault."},
                {"from": "PROTECTION_TRIPPED", "to": "CONFIGURED_OUTPUT_OFF", "rule": "Remove cause, force output off, clear protection, verify cleared."},
                {"from": "ANY_CONNECTED", "to": "DISCONNECTED", "rule": "Shutdown then disconnect; investigate any cleanup failure."},
                {"from": "ANY", "to": "FAULTED", "rule": "Unresolved communication, command, verification, or safety error."},
            ],
        },
        "resources": {
            "consumed": [
                {"id": "visa_resource", "type": "exclusive", "description": "VISA resource string for USB/LAN/vendor transport."},
                {"id": "tcp_socket", "type": "exclusive", "description": "Host and TCP port, normally 5025."},
                {"id": "session_alias", "type": "exclusive_within_library", "description": "Unique named session."},
                {"id": "mainframe_channel", "type": "exclusive_for_mutation", "description": "Channel 1..4; coordinate concurrent test ownership."},
            ],
            "provided": [
                {"id": "dc_source", "quantity": ["voltage", "current", "power"], "availability": "module-dependent"},
                {"id": "smu", "quantity": ["source_voltage", "source_current", "measure_voltage", "measure_current"], "availability": "SMU module-dependent"},
                {"id": "electronic_load", "quantity": ["cc", "cv", "cr", "cp"], "availability": "verified module-dependent; real load modules remain restricted unless explicitly supported"},
                {"id": "internal_measurement", "quantity": ["voltage", "current", "power"], "availability": "module-dependent"},
            ],
        },
        "dependencies": {
            "runtime": ["Python >=3.10", "Robot Framework >=7,<9", "PyVISA >=1.14"],
            "optional": ["pyvisa-py >=0.7 when no vendor VISA backend is installed"],
            "external": ["Keysight IO Libraries Suite or another compatible VISA backend for VISA resources", "Network reachability for raw Ethernet", "Reviewed cabling, fixtures, DUT limits, and interlocks"],
        },
        "capabilities": [capability(item) for item in keywords],
        "error_catalogue": [
            {"id": "N6700Error", "meaning": "Base driver failure.", "planner_action": "Stop the affected workflow and classify the concrete subtype."},
            {"id": "N6700ConnectionError", "meaning": "Connection could not open or remain usable.", "planner_action": "Do not energize; verify resource ownership, cable, address, and backend."},
            {"id": "N6700TimeoutError", "meaning": "Transport or instrument operation timed out.", "planner_action": "Query/verify actual state before any retry."},
            {"id": "N6700CommunicationError", "meaning": "Protocol or transport communication failure.", "planner_action": "Enter safe state if communication is available; otherwise use bench emergency procedure."},
            {"id": "N6700CommandError", "meaning": "Instrument rejected a command or reported SCPI errors.", "planner_action": "Drain errors, correct command/capability assumptions, do not blind-retry."},
            {"id": "N6700ProtectionError", "meaning": "Protection event prevented operation.", "planner_action": "Remove electrical cause, disable output, clear and verify protection."},
            {"id": "N6700QueryInterruptedError", "meaning": "Pending query response was interrupted.", "planner_action": "Serialize access and recover the session before continuing."},
            {"id": "UnsupportedFeatureError", "meaning": "Installed module/transport lacks requested verified feature.", "planner_action": "Select another capability or mark requirement unsupported."},
            {"id": "InvalidChannelError", "meaning": "Requested channel is invalid or unavailable.", "planner_action": "Discover modules and correct channel mapping."},
            {"id": "SafetyInterlockError", "meaning": "Inhibit/interlock prevents operation.", "planner_action": "Do not bypass; follow operator and bench safety procedure."},
            {"id": "ValueError", "meaning": "Robot argument or engineering value is invalid.", "planner_action": "Correct test data before hardware execution."},
            {"id": "RuntimeError", "meaning": "Session alias or library state is invalid.", "planner_action": "Correct setup/teardown ordering."},
        ],
        "safety_rules": [
            {"id": "SAFE-001", "severity": "critical", "rule": "Never enable a source output or load input until wiring, polarity, DUT absolute maxima, current limit, voltage limit, and protection thresholds are approved."},
            {"id": "SAFE-002", "severity": "critical", "rule": "Treat Write N6700 SCPI as unrestricted. Use typed keywords unless the exact command is reviewed and represented in the test plan."},
            {"id": "SAFE-003", "severity": "high", "rule": "Connect non-invasively. Keep reset_on_connect and clear_errors_on_connect false unless the test owns the complete bench state."},
            {"id": "SAFE-004", "severity": "high", "rule": "After connect, query output/load-input and protection states; do not assume the instrument is de-energized."},
            {"id": "SAFE-005", "severity": "high", "rule": "Clear protection only after removing the root cause and disabling the affected channel. Do not restore output automatically unless explicitly justified."},
            {"id": "SAFE-006", "severity": "high", "rule": "A software shutdown attempt is not an emergency stop. Bench hardware interlocks and operator disconnect procedures remain mandatory."},
            {"id": "SAFE-007", "severity": "medium", "rule": "Serialize state-changing operations per session/channel; query interruption and race conditions are unsafe."},
            {"id": "SAFE-008", "severity": "medium", "rule": "Apply DUT-specific settling time after every energization or setpoint step before judging measurements."},
            {"id": "SAFE-009", "severity": "high", "rule": "Real electronic-load operation is prohibited unless the installed module is explicitly verified by the driver's module capability map and the bench contract."},
        ],
        "verification_objectives": [
            {"id": "VO-IDENTITY", "objective": "Connected instrument identity and firmware are captured.", "oracle": "manufacturer, model, serial and firmware are non-empty and match the approved bench record."},
            {"id": "VO-MODULE-MAP", "objective": "Installed modules and capabilities are known before channel use.", "oracle": "Discover N6700 Modules returns each planned channel and required capability."},
            {"id": "VO-SAFE-START", "objective": "Planned channels start de-energized.", "oracle": "Get N6700 Output State or Get N6700 Load Input State is false for every owned channel."},
            {"id": "VO-SETPOINT", "objective": "Programmed setpoints and protection are accepted.", "oracle": "Readback equals requested value within instrument resolution and Check N6700 Errors passes."},
            {"id": "VO-OUTPUT", "objective": "Output/input state follows explicit commands.", "oracle": "State readback matches requested boolean and no protection is active."},
            {"id": "VO-MEASUREMENT", "objective": "Measured quantity satisfies approved limits.", "oracle": "Built-in Should Be keyword passes or explicit numeric comparison uses approved tolerance."},
            {"id": "VO-PROTECTION", "objective": "Protection behavior is observable and recoverable without automatic re-energization.", "oracle": "Trip is reported, channel is off, cause removed, clear succeeds, output remains off by default."},
            {"id": "VO-SHUTDOWN", "objective": "All controlled energy paths are disabled at test end.", "oracle": "Shutdown All N6700 Channels reports success and state readback confirms off before disconnect."},
        ],
        "setup_teardown_contract": {
            "recommended_library_import": "Library    KeysightN6700Library    auto_shutdown=${TRUE}    strict_errors=${TRUE}",
            "setup_sequence": [
                "Connect with a unique alias using non-invasive defaults.",
                "Capture identity and firmware.",
                "Discover installed modules and validate required capabilities.",
                "Read output/load-input and protection state for every owned channel.",
                "Force owned channels off before applying configuration.",
                "Program conservative limits and verify SCPI error queue is empty.",
            ],
            "teardown_sequence": [
                "Disable each active output/load input.",
                "Call Shutdown All N6700 Channels and record the result.",
                "Check/drain errors and capture final protection state when relevant.",
                "Disconnect N6700 or Disconnect All N6700.",
                "Escalate any shutdown/close failure; do not report a clean test solely because teardown continued.",
            ],
            "failure_teardown": "Use Run Keyword And Ignore Error only to continue collecting shutdown evidence; preserve the original failure and any cleanup failure.",
        },
        "limitations": [
            "Channel address validation is 1..4; actual installed channel count and module types must be discovered.",
            "Module electrical ranges are not globally hard-coded in the Robot adapter; the instrument/module and approved bench limits are authoritative.",
            "Internal measurements are not a substitute for an independently calibrated DMM when traceable accuracy is required.",
            "Real electronic-load commands remain intentionally restricted for unverified physical load modules; the bundled SIM_LOAD is intended for automated tests.",
            "No driver keyword can prove external wiring, polarity, fixture rating, DUT state, or emergency-stop availability.",
            "Raw SCPI may access functionality not represented by this contract and invalidates capability-level safety assumptions.",
            "Automatic shutdown is best-effort and can fail during transport loss or hardware fault.",
        ],
        "planning_hints": [
            "Prefer typed keywords over raw SCPI.",
            "Start with identity, module discovery, and read-only state capture.",
            "Configure limits while output/load input is off, then verify readback before enabling.",
            "Use one alias per physical mainframe and reserve channels explicitly in multi-driver plans.",
            "After setpoint or output changes, apply stabilization from the requirement or system bench contract before measurement.",
            "Use an external DMM as preferred source when the system contract declares one for voltage/current accuracy.",
            "End every energy-producing or sinking workflow with explicit off verification and shutdown evidence.",
        ],
        "unknown_handling": {
            "policy": "fail_closed",
            "rules": [
                "UNKNOWN module capability: do not issue state-changing channel commands.",
                "UNKNOWN wiring or DUT limits: do not enable output/load input.",
                "UNKNOWN stabilization time: require an approved test-plan value before pass/fail measurement.",
                "UNKNOWN protection/interlock state: command off and request operator review.",
                "UNKNOWN result after timeout/communication loss: treat state as potentially energized and invoke bench emergency workflow.",
                "UNKNOWN raw SCPI effect: prohibit command.",
            ],
        },
        "conformance_rules": {
            "keyword_coverage": "Exactly one capability entry must exist for every @keyword in KeysightN6700Library/library.py.",
            "required_capability_fields": ["signature", "purpose", "inputs", "outputs", "preconditions", "postconditions", "side_effects", "risk_level", "timing", "retry_policy", "errors", "exclusive_resources"],
            "lock_rule": "ai/keysight_n6700_ai_contract.lock hashes the driver contract, system contract, library source, generator, and exact ordered keyword list.",
            "generation_rule": "Run python scripts/generate_ai_contract.py after any public keyword, signature, documentation, version, safety, or bench-template change.",
            "verification_rule": "CI and package verification must run python scripts/generate_ai_contract.py --check.",
        },
    }


def build_system_contract(version: str, release: str) -> dict[str, Any]:
    return {
        "contract_standard": {"id": "RFDS-018", "version": "1.0", "status": "draft-source-conformant"},
        "contract_version": "1.0",
        "identity": {
            "bench_id": "keysight_n6700_standalone_template",
            "name": "Keysight N6700 standalone bench contract template",
            "status": "REQUIRES_SITE_CONFIGURATION",
            "release": release,
            "purpose": "Safe default bench model shipped with the driver. It is not authorization to energize a DUT until UNKNOWN topology and limits are replaced by site-specific approved values.",
        },
        "available_drivers": [
            {
                "driver_id": "keysight_n6700",
                "version": version,
                "robot_library": "KeysightN6700Library",
                "contract": "ai/keysight_n6700_ai_contract.yaml",
                "role": ["programmable_dc_source", "smu", "internal_voltage_current_power_measurement", "verified_module_dependent_electronic_load"],
            }
        ],
        "physical_topology": {
            "instruments": [{"id": "n6700_mainframe_1", "driver_id": "keysight_n6700", "resource": N6775A_USB_RESOURCE, "transport": "usb_visa", "channels": [1, 2, 3, 4]}],
            "connections": [
                {"from": "n6700_mainframe_1.channel[1..4].output", "to": "UNKNOWN_DUT_OR_FIXTURE", "polarity": "UNKNOWN", "wire_rating": "UNKNOWN", "status": "BLOCKS_ENERGIZATION"}
            ],
            "required_site_fields": ["installed module model per channel", "DUT/fixture connection per channel", "polarity", "wire/connector rating", "earth/reference scheme", "external interlock and emergency stop"],
        },
        "shared_resources": [
            {"id": "n6700_transport", "kind": "USB_VISA", "ownership": "exclusive", "address": N6775A_USB_RESOURCE},
            {"id": "n6700_session_main", "kind": "driver_alias", "ownership": "exclusive_within_test_process", "value": "main"},
            {"id": "n6700_channels", "kind": "electrical_channels", "ownership": "exclusive_for_state_change", "members": [1, 2, 3, 4]},
            {"id": "bench_mains_and_interlock", "kind": "safety_resource", "ownership": "operator/fixture", "status": "UNKNOWN"},
        ],
        "signal_graph": {
            "nodes": [
                {"id": "n6700_ch1_4_dc", "type": "bidirectional_module_dependent_dc_port", "producer": "keysight_n6700", "quantities": ["voltage", "current", "power"]},
                {"id": "dut_ports", "type": "consumer_or_source", "status": "UNKNOWN"},
            ],
            "edges": [{"from": "n6700_ch1_4_dc", "to": "dut_ports", "status": "UNKNOWN", "energization_allowed": False}],
        },
        "preferred_measurement_sources": [
            {"quantity": "channel_voltage", "preferred": "external_calibrated_dmm_when_traceability_or accuracy beyond module specification is required", "fallback": "N6700 internal measurement", "selection_rule": "System integrator must add the external DMM driver/connection before using it."},
            {"quantity": "channel_current", "preferred": "N6700 internal measurement for control/monitoring; external calibrated shunt/DMM for traceable verification", "fallback": "N6700 internal measurement"},
            {"quantity": "channel_power", "preferred": "computed from synchronized traceable voltage/current when required", "fallback": "N6700 internal power measurement"},
            {"quantity": "output_or_load_input_state", "preferred": "N6700 state readback", "fallback": "none"},
            {"quantity": "protection_state", "preferred": "N6700 protection status", "fallback": "operator/fixture indicators"},
        ],
        "requirement_coverage": [
            {"requirement_pattern": "identify programmable power instrument", "drivers": ["keysight_n6700"], "verification_objectives": ["VO-IDENTITY", "VO-MODULE-MAP"]},
            {"requirement_pattern": "apply controlled DC voltage/current", "drivers": ["keysight_n6700"], "verification_objectives": ["VO-SAFE-START", "VO-SETPOINT", "VO-OUTPUT", "VO-SHUTDOWN"], "status": "BLOCKED_UNTIL_TOPOLOGY_CONFIGURED"},
            {"requirement_pattern": "measure channel voltage/current/power", "drivers": ["keysight_n6700"], "verification_objectives": ["VO-MEASUREMENT"], "traceability_note": "Add independent measurement driver when required."},
            {"requirement_pattern": "verify protection behavior", "drivers": ["keysight_n6700"], "verification_objectives": ["VO-PROTECTION", "VO-SHUTDOWN"], "status": "REQUIRES_APPROVED_FAULT_INJECTION_PLAN"},
        ],
        "test_templates": [
            {
                "id": "TEMPLATE-READ-ONLY-DISCOVERY",
                "purpose": "Identify instrument and module map without intentional output changes.",
                "sequence": ["Connect To N6700", "Get N6700 Identity", "Discover N6700 Modules", "Get N6700 Protection Status per installed channel", "Get N6700 Output State or Load Input State", "Disconnect N6700"],
                "risk": "low_but_existing_output_state_unknown",
            },
            {
                "id": "TEMPLATE-SAFE-SOURCE-CHANNEL",
                "purpose": "Configure, energize, measure, and shut down one source/SMU channel.",
                "preconditions": ["Site topology complete", "DUT limits approved", "interlock available", "channel reserved"],
                "sequence": ["Connect and identify", "Discover modules", "Turn Off N6700 Output", "Configure limits with output=false", "Verify setpoint/protection readback", "Turn On N6700 Output", "Wait approved stabilization", "Measure/verify", "Turn Off N6700 Output", "Shutdown All N6700 Channels", "Disconnect"],
                "risk": "high",
            },
            {
                "id": "TEMPLATE-EMERGENCY-SHUTDOWN",
                "purpose": "Bench response to fault, timeout, unexpected value, or operator stop.",
                "sequence": ["Attempt Turn Off for known active channels", "Shutdown All N6700 Channels", "Use external interlock/emergency stop if software communication is absent or shutdown is not verified", "Record errors and final observed state", "Disconnect only after energy state is controlled"],
                "risk": "critical",
            },
        ],
        "bench_constraints": {
            "operator_actions": ["Verify wiring and polarity", "Set/confirm external interlock", "Approve DUT limits", "Remain available for first energization", "Use emergency disconnect when software shutdown is not verified"],
            "safety_zones": [{"id": "ZONE-DC-OUTPUT", "boundaries": "UNKNOWN", "maximum_voltage": "UNKNOWN", "maximum_current": "UNKNOWN", "status": "BLOCKS_ENERGIZATION"}],
            "maximum_simultaneous_operations": {"state_changing_per_session": 1, "same_channel": 1, "parallel_read_only": "Allowed only when transport serialization is guaranteed; default 1"},
            "environmental_limits": {"ambient_temperature": "UNKNOWN", "humidity": "UNKNOWN", "ventilation_clearance": "Follow instrument manual and site procedure"},
        },
        "scheduling_rules": [
            "Reserve the physical transport and alias exclusively for each test process.",
            "Reserve each channel exclusively for any state-changing workflow.",
            "Do not interleave raw SCPI with typed keywords from another task/session.",
            "Do not run self-test, reset, disconnect, or all-channel shutdown concurrently with channel operations.",
            "Apply stabilization from the requirement/topology; UNKNOWN stabilization blocks pass/fail measurement after energization.",
            "Default parallel execution limit is one state-changing operation for the mainframe.",
            "Order multi-driver workflows as measurement/interlock ready -> source configure off -> fixture/relay route -> source enable -> stabilize -> measure -> source off -> route safe.",
        ],
        "global_safety": {
            "forbidden_sequences": [
                "Enable output/load input while physical topology or limits are UNKNOWN.",
                "Route relays/connectors while an associated source output is energized unless the fixture is explicitly hot-switch rated and the plan approves it.",
                "Clear protection and automatically re-enable before the trip cause is removed.",
                "Blindly retry after timeout or communication loss.",
                "Use raw SCPI to bypass typed driver restrictions or bench safety rules.",
            ],
            "emergency_shutdown_workflow": [
                "Stop test sequencing and preserve the original error.",
                "Command all known source outputs and load inputs off.",
                "Call Shutdown All N6700 Channels and evaluate per-channel success.",
                "If communication is unavailable or any energy path cannot be verified off, activate the external interlock/emergency disconnect and notify the operator.",
                "Record identity, active test step, commands, errors, protection state, and observed final state.",
                "Do not resume until root cause and bench state are reviewed.",
            ],
        },
        "unknown_handling": {
            "policy": "fail_closed",
            "site_configuration_required": True,
            "blocking_unknowns": ["module map", "physical wiring", "polarity", "DUT limits", "safety-zone limits", "external interlock", "stabilization requirements"],
            "planner_rule": "An AI planner may generate a draft plan with explicit UNKNOWN placeholders, but must not generate an executable energizing sequence until all blocking unknowns are resolved and approved.",
        },
    }


def canonical_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=False, ensure_ascii=False) + "\n").encode("utf-8")


def generated_files(repo: Path) -> dict[Path, bytes]:
    version = parse_version(repo)
    release = release_from_version(version)
    source_path = repo / LIBRARY_SOURCE
    source = source_path.read_text(encoding="utf-8")
    keywords = parse_keywords(source)
    ai_contract_data = build_ai_contract(version, release, keywords)
    system_contract_data = build_system_contract(version, release)
    ai_bytes = canonical_bytes(ai_contract_data)
    system_bytes = canonical_bytes(system_contract_data)
    generator_path = repo / "scripts/generate_ai_contract.py"
    lock_data = {
        "lock_format": "RFDS-AI-CONTRACT-LOCK-1",
        "driver_id": "keysight_n6700",
        "driver_version": version,
        "release": release,
        "keyword_count": len(keywords),
        "keyword_names": [item.robot_keyword for item in keywords],
        "hashes": {
            "ai_contract_sha256": sha256_bytes(ai_bytes),
            "system_ai_contract_sha256": sha256_bytes(system_bytes),
            "library_source_sha256": sha256_path(source_path),
            "generator_sha256": sha256_path(generator_path),
        },
        "generation": {
            "command": "python scripts/generate_ai_contract.py",
            "deterministic": True,
            "yaml_encoding": "JSON-compatible YAML 1.2",
        },
    }
    return {
        AI_CONTRACT: ai_bytes,
        SYSTEM_CONTRACT: system_bytes,
        AI_LOCK: canonical_bytes(lock_data),
    }


def write_files(repo: Path) -> int:
    files = generated_files(repo)
    for relative, content in files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        print(f"WROTE {relative}")
    return 0


def check_files(repo: Path) -> int:
    errors: list[str] = []
    for relative, expected in generated_files(repo).items():
        path = repo / relative
        if not path.is_file():
            errors.append(f"missing {relative}")
            continue
        if path.read_bytes() != expected:
            errors.append(f"stale {relative}; run python scripts/generate_ai_contract.py")
        else:
            print(f"PASS {relative} is current")
    if errors:
        for error in errors:
            print(f"FAIL {error}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail when generated contracts are missing or stale")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if repo.name != ROOT_NAME:
        raise SystemExit(f"Repository folder must be exactly {ROOT_NAME!r}; got {repo.name!r}")
    return check_files(repo) if args.check else write_files(repo)


if __name__ == "__main__":
    raise SystemExit(main())
