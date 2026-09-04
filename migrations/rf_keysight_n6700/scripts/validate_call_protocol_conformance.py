"""Validate RFDS-019 N6775A keyword inventory and protocol vector coverage."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT_NAME = "rf_keysight_n6700"
LIBRARY = Path("KeysightN6700Library/library.py")
INVENTORY = Path("tests/conformance/data/keyword_inventory.yaml")
VECTORS = Path("tests/conformance/data/protocol_vectors.yaml")
EXCLUSIONS = Path("tests/conformance/data/exclusions.yaml")
SUITE = Path("tests/conformance/driver_call_protocol_conformance.robot")
DRIVER = Path("keysight_n6700/driver.py")
RESOURCE_KEYWORDS = Path("tests/conformance/resources/conformance_keywords.resource")


def load_json_yaml(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: invalid JSON-compatible YAML: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top level must be an object")
    return value


def public_keywords(source: str) -> list[str]:
    return re.findall(r'@keyword\("([^"]+)"\)', source)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    errors: list[str] = []
    checks: list[str] = []

    def check(condition: bool, ok: str, fail: str) -> None:
        (checks if condition else errors).append(ok if condition else fail)

    check(root.name == ROOT_NAME, f"fixed source root is {ROOT_NAME}/", f"source root must be {ROOT_NAME}/")
    required = [LIBRARY, INVENTORY, VECTORS, EXCLUSIONS, SUITE, DRIVER, RESOURCE_KEYWORDS]
    for relative in required:
        check((root / relative).is_file(), f"exists: {relative}", f"missing: {relative}")
    if errors:
        for message in errors:
            print(f"FAIL: {message}", file=sys.stderr)
        return 1

    library_source = (root / LIBRARY).read_text(encoding="utf-8")
    suite_source = (root / SUITE).read_text(encoding="utf-8")
    driver_source = (root / DRIVER).read_text(encoding="utf-8")
    resource_source = (root / RESOURCE_KEYWORDS).read_text(encoding="utf-8")
    exported = public_keywords(library_source)
    inventory_doc = load_json_yaml(root / INVENTORY)
    vectors_doc = load_json_yaml(root / VECTORS)
    exclusions_doc = load_json_yaml(root / EXCLUSIONS)
    inventory = inventory_doc.get("inventory", [])
    vectors = vectors_doc.get("vectors", [])
    exclusions = exclusions_doc.get("exclusions", [])

    check(inventory_doc.get("module_profile") == "N6775A", "inventory profile is N6775A", "inventory profile is not N6775A")
    check(vectors_doc.get("module_profile") == "N6775A", "vector profile is N6775A", "vector profile is not N6775A")
    check(exclusions_doc.get("module_profile") == "N6775A", "exclusion profile is N6775A", "exclusion profile is not N6775A")
    check(isinstance(inventory, list), "inventory is a list", "inventory must be a list")
    check(isinstance(vectors, list), "vectors are a list", "vectors must be a list")
    check(isinstance(exclusions, list), "exclusions are a list", "exclusions must be a list")
    if not all(isinstance(value, list) for value in (inventory, vectors, exclusions)):
        return 1

    inventory_names = [item.get("public_keyword") for item in inventory if isinstance(item, dict)]
    vector_names = [item.get("keyword") for item in vectors if isinstance(item, dict)]
    excluded_names = [item.get("keyword") for item in exclusions if isinstance(item, dict)]
    check(len(exported) == 63, f"library exports {len(exported)} keywords", f"expected 63 exported keywords, got {len(exported)}")
    check(inventory_doc.get("public_keyword_count") == len(exported), "declared inventory count matches library", "declared inventory count is stale")
    check(inventory_names == exported, "inventory exactly matches ordered public keyword API", "inventory does not exactly match public keyword API")
    check(len(set(vector_names)) == len(vector_names), "protocol vector keyword names are unique", "duplicate protocol vector keyword")
    check(len(set(excluded_names)) == len(excluded_names), "exclusion keyword names are unique", "duplicate exclusion keyword")
    check(not (set(vector_names) & set(excluded_names)), "vectors and exclusions do not overlap", "a keyword is both vectored and excluded")
    check(set(vector_names) | set(excluded_names) == set(exported), "every public keyword has a vector or exclusion", "one or more public keywords lack vector/exclusion coverage")

    required_vector_fields = {
        "id", "keyword", "driver_method", "test_case", "arguments", "preconditions",
        "expected_outbound", "expected_inbound", "expected_return", "risk_level", "cleanup",
    }
    incomplete = [
        str(item.get("id", "<unnamed>"))
        for item in vectors
        if isinstance(item, dict) and (required_vector_fields - set(item))
    ]
    check(not incomplete, "all protocol vectors contain mandatory fields", f"incomplete vectors: {incomplete[:5]}")
    bad_ids = [item.get("id") for item in vectors if not str(item.get("id", "")).startswith("N6775A-")]
    check(not bad_ids, "all vectors use N6775A identifiers", f"non-N6775A vector IDs: {bad_ids[:5]}")
    missing_suite_refs: list[str] = []
    for item in vectors:
        if not isinstance(item, dict):
            continue
        refs = str(item.get("test_case", ""))
        for ref in (part.strip() for part in refs.split(",")):
            if ref.isdigit() and not re.search(rf"(?m)^0?{int(ref)}\s+", suite_source):
                missing_suite_refs.append(f"{item.get('id')}->{ref}")
    check(not missing_suite_refs, "every vector references an existing Robot test", f"missing Robot test references: {missing_suite_refs[:8]}")

    required_suite_markers = [
        "Suite Setup      Prepare N6775A Self Check",
        "Suite Teardown   Restore Safe Channel State And Disconnect",
        "14 Invalid SCPI Produces Error And Communication Recovers",
        "16 N6775A Rejects SMU And Electronic Load Keywords Correctly",
        "21 Protocol Trace Contains Required Command Families And Responses",
    ]
    for marker in required_suite_markers:
        check(marker in suite_source, f"suite marker present: {marker}", f"suite marker missing: {marker}")
    check("_append_protocol_trace" in driver_source and '"response": response' in driver_source,
          "transport-boundary audit captures commands and responses",
          "driver protocol trace implementation is missing")
    check(
        "Normalize Runtime Boolean Variables" in resource_source
        and resource_source.count("Convert To Boolean") >= 3,
        "CLI boolean variables are normalized before expression evaluation",
        "N6775A setup does not normalize CLI boolean strings",
    )
    unsafe_boolean_expressions = re.findall(
        r"Skip If\s+not \${(?:HIL_ENABLE|ALLOW_RESET|ALLOW_ACTIVE_OUTPUT)}",
        suite_source + "\n" + resource_source,
    )
    check(
        not unsafe_boolean_expressions,
        "boolean guards preserve Robot variable types",
        "unsafe lowercase-string boolean expression remains in self-check",
    )
    check(
        "clear_errors_on_connect=${TRUE}" in resource_source,
        "real-device self-check drains stale errors while connecting",
        "real-device self-check does not drain stale errors while connecting",
    )
    prepare_start = resource_source.find("Prepare N6775A Self Check")
    clear_pos = resource_source.find("Clear N6700 Status", prepare_start)
    output_off_pos = resource_source.find("Turn Off N6700 Output", prepare_start)
    check(
        prepare_start >= 0 and clear_pos >= 0 and output_off_pos >= 0 and clear_pos < output_off_pos,
        "self-check clears status before the first strict-checked output command",
        "self-check must clear status before the first strict-checked output command",
    )

    check(
        "Convert To Integer    ${CHANNEL}" in resource_source
        and "Set Suite Variable    ${CHANNEL}" in resource_source
        and "${CHANNEL_KEY}" in suite_source,
        "channel input is normalized to integer while dictionary keys use explicit strings",
        "N6775A self-check channel typing is not deterministic",
    )
    check(
        re.search(r"(?m)^\s*\$\{channel\}=", suite_source) is None,
        "local variables do not shadow the case-insensitive ${CHANNEL} suite variable",
        "a local ${channel} variable shadows ${CHANNEL}",
    )
    power_vector_ids = {
        "N6775A-MEASURE_N6700_POWER",
        "N6775A-MEASURE_N6700_CHANNEL",
        "N6775A-MEASURE_ALL_N6700_CHANNELS",
        "N6775A-N6700_POWER_SHOULD_BE",
    }
    direct_power_vectors: list[str] = []
    missing_forbidden_power: list[str] = []
    for item in vectors:
        if not isinstance(item, dict) or item.get("id") not in power_vector_ids:
            continue
        outbound = item.get("expected_outbound", {})
        operations = outbound.get("operations", []) if isinstance(outbound, dict) else []
        forbidden = outbound.get("forbidden_operations", []) if isinstance(outbound, dict) else []
        if any(str(operation).strip().upper().startswith("MEAS:POW?") for operation in operations):
            direct_power_vectors.append(str(item.get("id")))
        if "MEAS:POW? (@ch)" not in forbidden:
            missing_forbidden_power.append(str(item.get("id")))
    check(
        not direct_power_vectors and not missing_forbidden_power,
        "N6775A vectors calculate power without direct MEAS:POW?",
        f"invalid N6775A power vectors: direct={direct_power_vectors}, missing_forbidden={missing_forbidden_power}",
    )

    for message in checks:
        print(f"PASS: {message}")
    for message in errors:
        print(f"FAIL: {message}", file=sys.stderr)
    print(f"Result: {len(checks)} passed, {len(errors)} failed")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
