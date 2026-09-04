"""Verify Robot Framework Driver project package structure and release consistency."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

ROOT_NAME = "rf_keysight_n6700"
DRIVER_NAME = "keysight_n6700"
MIN_EXAMPLES = 10
VERSION_RE = re.compile(r'^version\s*=\s*"(?P<version>\d+\.\d+\.\d+)"\s*$', re.MULTILINE)


@dataclass
class ValidationResult:
    checks: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def check(self, condition: bool, success: str, error: str) -> None:
        if condition:
            self.checks.append(success)
        else:
            self.errors.append(error)

    def report(self) -> int:
        for message in self.checks:
            print(f"PASS: {message}")
        for message in self.errors:
            print(f"FAIL: {message}", file=sys.stderr)
        print(f"Result: {len(self.checks)} passed, {len(self.errors)} failed")
        return 1 if self.errors else 0


def release_from_python_version(version: str) -> str:
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError(f"Unsupported Python package version: {version!r}")
    year, release, _patch = (int(part) for part in parts)
    return f"{year:02d}.{release:02d}"


def parse_project_version(pyproject_text: str) -> str:
    match = VERSION_RE.search(pyproject_text)
    if match is None:
        raise ValueError("Could not find [project] version in pyproject.toml")
    return match.group("version")


def expected_archive_name(release: str) -> str:
    return f"{ROOT_NAME}_v{release}.zip"


def required_paths(release: str) -> tuple[str, ...]:
    return (
        "README.md",
        "ai/README.md",
        "ai/keysight_n6700_ai_contract.yaml",
        "ai/keysight_n6700_ai_contract.lock",
        "system_ai_contract.yaml",
        "standards/RFDS-017_AI_Driver_Contract_v3.0.md",
        "standards/RFDS-018_AI_Test_Bench_Contract_v1.0.md",
        "standards/RFDS-019_Robot_Framework_Driver_Call_and_Protocol_Conformance_Test_Specification_v1.1.md",
        "PROJECT_REQUIREMENTS.md",
        "RELEASE_INFO.json",
        "CHANGELOG.md",
        "PACKAGE_MANIFEST.md",
        "pyproject.toml",
        "mkdocs.yml",
        "KeysightN6700Library/library.py",
        "KeysightN6700Library/version.py",
        "keysight_n6700/driver.py",
        "history/README.md",
        f"history/v{release}.md",
        "review/README.md",
        f"review/v{release}_code_review.md",
        f"review/v{release}_package_compliance_review.md",
        "guide/pycharm_robot_framework_setup.md",
        "guide/installation.md",
        "guide/writing_robot_tests.md",
        "guide/hardware_connection.md",
        "examples/README.md",
        "scripts/run_example.bat",
        "scripts/run_example.ps1",
        "scripts/run_example.sh",
        "scripts/run_all_examples.bat",
        "scripts/run_all_examples.ps1",
        "scripts/run_all_examples.sh",
        "scripts/verify_package.bat",
        "scripts/verify_package.ps1",
        "scripts/verify_package.sh",
        "scripts/verify_project_package.py",
        "scripts/make_release.py",
        "scripts/generate_ai_contract.py",
        "scripts/validate_call_protocol_conformance.py",
        "scripts/summarize_n6775a_self_check.py",
        "scripts/run_n6775a_self_check.bat",
        "scripts/run_n6775a_self_check.ps1",
        "scripts/run_n6775a_self_check.sh",
        "tests/conformance/driver_call_protocol_conformance.robot",
        "tests/conformance/resources/conformance_keywords.resource",
        "tests/conformance/resources/conformance_variables.resource",
        "tests/conformance/data/keyword_inventory.yaml",
        "tests/conformance/data/protocol_vectors.yaml",
        "tests/conformance/data/exclusions.yaml",
        "tests/conformance/expected/response_schemas/n6775a_responses.json",
        "docs/index.md",
        "docs/ai_contracts.md",
        "docs/project_package_standard.md",
        "docs/n6775a_self_check.md",
        "docs/KeysightN6700Library.html",
        ".github/workflows/ci.yml",
        ".github/workflows/pages.yml",
    )


def required_artifacts(version: str) -> tuple[str, ...]:
    return (
        f"dist/robotframework_keysight_n6700-{version}-py3-none-any.whl",
        f"dist/robotframework_keysight_n6700-{version}.tar.gz",
        "SHA256SUMS.txt",
    )



def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_robot_keywords(library_source: str) -> list[str]:
    return re.findall(r'@keyword\("([^"]+)"\)', library_source)


def validate_ai_contracts(
    *,
    names: set[str],
    read_text: Callable[[str], str],
    version: str,
    release: str,
    result: ValidationResult,
) -> None:
    required = {
        "ai/keysight_n6700_ai_contract.yaml",
        "ai/keysight_n6700_ai_contract.lock",
        "system_ai_contract.yaml",
        "scripts/generate_ai_contract.py",
        "scripts/validate_call_protocol_conformance.py",
        "scripts/summarize_n6775a_self_check.py",
        "scripts/run_n6775a_self_check.bat",
        "scripts/run_n6775a_self_check.ps1",
        "scripts/run_n6775a_self_check.sh",
        "tests/conformance/driver_call_protocol_conformance.robot",
        "tests/conformance/resources/conformance_keywords.resource",
        "tests/conformance/resources/conformance_variables.resource",
        "tests/conformance/data/keyword_inventory.yaml",
        "tests/conformance/data/protocol_vectors.yaml",
        "tests/conformance/data/exclusions.yaml",
        "tests/conformance/expected/response_schemas/n6775a_responses.json",
        "KeysightN6700Library/library.py",
    }
    if not required.issubset(names):
        return

    try:
        contract = json.loads(read_text("ai/keysight_n6700_ai_contract.yaml"))
        lock = json.loads(read_text("ai/keysight_n6700_ai_contract.lock"))
        system_contract = json.loads(read_text("system_ai_contract.yaml"))
    except json.JSONDecodeError as exc:
        result.errors.append(f"AI contract is not valid JSON-compatible YAML: {exc}")
        return

    mandatory_driver_sections = {
        "identity",
        "mental_model",
        "state_machine",
        "resources",
        "dependencies",
        "capabilities",
        "error_catalogue",
        "safety_rules",
        "verification_objectives",
        "setup_teardown_contract",
        "limitations",
        "planning_hints",
        "unknown_handling",
        "conformance_rules",
    }
    missing_driver = sorted(mandatory_driver_sections - set(contract))
    result.check(
        not missing_driver,
        "RFDS-017 driver contract contains all mandatory sections",
        f"RFDS-017 driver contract missing sections: {missing_driver}",
    )

    identity = contract.get("identity", {})
    result.check(
        identity.get("python_version") == version and identity.get("release") == release,
        "RFDS-017 identity matches current release",
        "RFDS-017 identity has stale version/release metadata",
    )

    source = read_text("KeysightN6700Library/library.py")
    source_keywords = extract_robot_keywords(source)
    capabilities = contract.get("capabilities", [])
    capability_names = [item.get("robot_keyword") for item in capabilities if isinstance(item, dict)]
    result.check(
        capability_names == source_keywords,
        f"RFDS-017 capability coverage matches all {len(source_keywords)} Robot keywords",
        "RFDS-017 capability list does not exactly match the ordered public Robot keyword list",
    )

    required_capability_fields = {
        "signature",
        "purpose",
        "inputs",
        "outputs",
        "preconditions",
        "postconditions",
        "side_effects",
        "risk_level",
        "timing",
        "retry_policy",
        "errors",
        "exclusive_resources",
    }
    incomplete: list[str] = []
    for item in capabilities:
        if not isinstance(item, dict):
            incomplete.append("<non-object capability>")
            continue
        missing = required_capability_fields - set(item)
        if missing:
            incomplete.append(f"{item.get('robot_keyword', '<unnamed>')}: {sorted(missing)}")
    result.check(
        not incomplete,
        "every RFDS-017 capability contains mandatory semantics",
        "incomplete RFDS-017 capabilities: " + "; ".join(incomplete[:5]),
    )

    hashes = lock.get("hashes", {})
    expected_hashes = {
        "ai_contract_sha256": sha256_text(read_text("ai/keysight_n6700_ai_contract.yaml")),
        "system_ai_contract_sha256": sha256_text(read_text("system_ai_contract.yaml")),
        "library_source_sha256": sha256_text(source),
        "generator_sha256": sha256_text(read_text("scripts/generate_ai_contract.py")),
    }
    hash_errors = [
        key for key, expected in expected_hashes.items() if hashes.get(key) != expected
    ]
    result.check(
        not hash_errors,
        "AI contract lock hashes are current",
        f"AI contract lock has stale hashes: {hash_errors}",
    )
    result.check(
        lock.get("keyword_names") == source_keywords
        and lock.get("keyword_count") == len(source_keywords)
        and lock.get("driver_version") == version
        and lock.get("release") == release,
        "AI contract lock keyword/version metadata is current",
        "AI contract lock keyword/version metadata is stale",
    )

    mandatory_system_sections = {
        "available_drivers",
        "physical_topology",
        "shared_resources",
        "signal_graph",
        "preferred_measurement_sources",
        "requirement_coverage",
        "test_templates",
        "bench_constraints",
        "scheduling_rules",
        "global_safety",
    }
    missing_system = sorted(mandatory_system_sections - set(system_contract))
    result.check(
        not missing_system,
        "RFDS-018 bench contract contains all mandatory sections",
        f"RFDS-018 bench contract missing sections: {missing_system}",
    )
    drivers = system_contract.get("available_drivers", [])
    driver_match = any(
        isinstance(item, dict)
        and item.get("driver_id") == DRIVER_NAME
        and item.get("version") == version
        and item.get("contract") == "ai/keysight_n6700_ai_contract.yaml"
        for item in drivers
    )
    result.check(
        driver_match,
        "RFDS-018 bench contract references the current driver contract/version",
        "RFDS-018 bench contract does not reference the current driver contract/version",
    )
    unknown = system_contract.get("unknown_handling", {})
    result.check(
        unknown.get("policy") == "fail_closed"
        and unknown.get("site_configuration_required") is True,
        "RFDS-018 template fails closed until site configuration is complete",
        "RFDS-018 UNKNOWN handling must fail closed and require site configuration",
    )

def validate_rfds_019(
    *,
    names: set[str],
    read_text: Callable[[str], str],
    result: ValidationResult,
) -> None:
    required = {
        "KeysightN6700Library/library.py",
        "keysight_n6700/driver.py",
        "tests/conformance/driver_call_protocol_conformance.robot",
        "tests/conformance/data/keyword_inventory.yaml",
        "tests/conformance/data/protocol_vectors.yaml",
        "tests/conformance/data/exclusions.yaml",
    }
    if not required.issubset(names):
        return
    try:
        inventory_doc = json.loads(read_text("tests/conformance/data/keyword_inventory.yaml"))
        vectors_doc = json.loads(read_text("tests/conformance/data/protocol_vectors.yaml"))
        exclusions_doc = json.loads(read_text("tests/conformance/data/exclusions.yaml"))
    except json.JSONDecodeError as exc:
        result.errors.append(f"RFDS-019 data is not valid JSON-compatible YAML: {exc}")
        return
    source_keywords = extract_robot_keywords(read_text("KeysightN6700Library/library.py"))
    inventory = inventory_doc.get("inventory", [])
    vectors = vectors_doc.get("vectors", [])
    exclusions = exclusions_doc.get("exclusions", [])
    inventory_names = [item.get("public_keyword") for item in inventory if isinstance(item, dict)]
    vector_names = [item.get("keyword") for item in vectors if isinstance(item, dict)]
    exclusion_names = [item.get("keyword") for item in exclusions if isinstance(item, dict)]
    result.check(
        inventory_doc.get("module_profile") == "N6775A"
        and vectors_doc.get("module_profile") == "N6775A"
        and exclusions_doc.get("module_profile") == "N6775A",
        "RFDS-019 data uses the N6775A profile",
        "RFDS-019 inventory/vector/exclusion profile must be N6775A",
    )
    result.check(
        inventory_names == source_keywords
        and inventory_doc.get("public_keyword_count") == len(source_keywords),
        f"RFDS-019 inventory matches all {len(source_keywords)} public keywords",
        "RFDS-019 keyword inventory does not exactly match the public API",
    )
    result.check(
        not (set(vector_names) & set(exclusion_names))
        and set(vector_names) | set(exclusion_names) == set(source_keywords),
        f"RFDS-019 coverage is complete: {len(vector_names)} vectors, {len(exclusion_names)} exclusions",
        "every public keyword must have exactly one RFDS-019 vector or exclusion",
    )
    required_fields = {
        "id", "keyword", "driver_method", "test_case", "arguments", "preconditions",
        "expected_outbound", "expected_inbound", "expected_return", "risk_level", "cleanup",
    }
    incomplete = [
        str(item.get("id", "<unnamed>"))
        for item in vectors
        if isinstance(item, dict) and required_fields - set(item)
    ]
    result.check(
        not incomplete,
        "all RFDS-019 protocol vectors contain mandatory fields",
        f"incomplete RFDS-019 vectors: {incomplete[:5]}",
    )
    suite = read_text("tests/conformance/driver_call_protocol_conformance.robot")
    result.check(
        "Prepare N6775A Self Check" in suite
        and "Restore Safe Channel State And Disconnect" in suite
        and "Invalid SCPI Produces Error And Communication Recovers" in suite
        and "Protocol Trace Contains Required Command Families And Responses" in suite,
        "N6775A Robot suite includes setup, safe teardown, error recovery, and trace verification",
        "N6775A Robot suite is missing mandatory workflow coverage",
    )
    driver = read_text("keysight_n6700/driver.py")
    result.check(
        "_append_protocol_trace" in driver and '"response": response' in driver,
        "driver captures outbound and inbound protocol evidence",
        "transport-boundary protocol trace capture is missing",
    )


def validate_common(
    *,
    names: set[str],
    read_text: Callable[[str], str],
    release: str,
    require_artifacts: bool,
    result: ValidationResult,
) -> None:
    for required in required_paths(release):
        result.check(required in names, f"required path exists: {required}", f"missing required path: {required}")

    result.check(
        not any(PurePosixPath(name).parts and PurePosixPath(name).parts[0] == "src" for name in names),
        "root package layout has no src/ directory",
        "src/ layout is prohibited by the project standard",
    )

    pyproject = read_text("pyproject.toml")
    version = parse_project_version(pyproject)
    derived_release = release_from_python_version(version)
    result.check(
        derived_release == release,
        f"Python version {version} maps to release {release}",
        f"Python version {version} maps to {derived_release}, not expected release {release}",
    )

    release_info = json.loads(read_text("RELEASE_INFO.json"))
    expected_info = {
        "driver_name": DRIVER_NAME,
        "release": release,
        "python_version": version,
        "archive": expected_archive_name(release),
        "internal_root": ROOT_NAME,
        "robot_library": "KeysightN6700Library",
        "ai_driver_contract": "ai/keysight_n6700_ai_contract.yaml",
        "ai_test_bench_contract": "system_ai_contract.yaml",
        "rfds_017": "3.0",
        "rfds_018": "1.0",
        "rfds_019": "1.1",
        "rfds_019_suite": "tests/conformance/driver_call_protocol_conformance.robot",
        "hardware_profile": "N6775A",
    }
    for key, expected in expected_info.items():
        actual = release_info.get(key)
        result.check(
            actual == expected,
            f"RELEASE_INFO.json {key} is current",
            f"RELEASE_INFO.json {key}={actual!r}; expected {expected!r}",
        )

    robot_examples = sorted(name for name in names if name.startswith("examples/robot/") and name.endswith(".robot"))
    python_examples = sorted(name for name in names if name.startswith("examples/python/") and name.endswith(".py"))
    result.check(
        len(robot_examples) >= MIN_EXAMPLES,
        f"Robot examples: {len(robot_examples)} (minimum {MIN_EXAMPLES})",
        f"only {len(robot_examples)} Robot examples; minimum is {MIN_EXAMPLES}",
    )
    result.check(
        len(robot_examples) + len(python_examples) >= MIN_EXAMPLES,
        f"total executable examples: {len(robot_examples) + len(python_examples)}",
        "fewer than ten executable examples in examples/",
    )

    archive_name = expected_archive_name(release)
    for document in ("README.md", "PROJECT_REQUIREMENTS.md", "PACKAGE_MANIFEST.md", "docs/index.md"):
        text = read_text(document)
        result.check(
            archive_name in text or document == "docs/index.md",
            f"{document} references current archive/release",
            f"{document} does not reference {archive_name}",
        )
        result.check(
            version in text,
            f"{document} references Python version {version}",
            f"{document} does not reference Python version {version}",
        )

    changelog = read_text("CHANGELOG.md")
    result.check(
        f"## v{release} / {version}" in changelog,
        "CHANGELOG.md contains the current release heading",
        f"CHANGELOG.md is missing heading for v{release} / {version}",
    )

    history = read_text(f"history/v{release}.md")
    result.check(
        archive_name in history and version in history,
        "current history record contains archive and Python version",
        "current history record has stale release metadata",
    )

    review = read_text(f"review/v{release}_code_review.md")
    result.check(
        "Change-by-change review" in review,
        "current code review covers each package change",
        "current code review lacks a change-by-change review section",
    )

    pages_workflow = read_text(".github/workflows/pages.yml")
    result.check(
        "mkdocs build --strict" in pages_workflow and "deploy-pages" in pages_workflow,
        "GitHub Pages workflow builds and deploys strict MkDocs output",
        "GitHub Pages workflow is incomplete",
    )

    validate_ai_contracts(
        names=names,
        read_text=read_text,
        version=version,
        release=release,
        result=result,
    )

    validate_rfds_019(
        names=names,
        read_text=read_text,
        result=result,
    )

    if require_artifacts:
        for artifact in required_artifacts(version):
            result.check(artifact in names, f"current build artifact exists: {artifact}", f"missing build artifact: {artifact}")
        libdoc = read_text("docs/KeysightN6700Library.html")
        result.check(
            f'"version": "{version}"' in libdoc,
            f"Libdoc reports version {version}",
            f"Libdoc does not report version {version}; regenerate it",
        )


def validate_source(source: Path, release: str, require_artifacts: bool) -> ValidationResult:
    result = ValidationResult()
    source = source.resolve()
    result.check(source.name == ROOT_NAME, f"source root is {ROOT_NAME}/", f"source folder must be named {ROOT_NAME!r}; got {source.name!r}")

    names = {path.relative_to(source).as_posix() for path in source.rglob("*") if path.is_file()}

    def read_text(name: str) -> str:
        path = source / name
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")

    validate_common(
        names=names,
        read_text=read_text,
        release=release,
        require_artifacts=require_artifacts,
        result=result,
    )
    return result


def validate_archive(archive: Path, release: str, require_artifacts: bool) -> ValidationResult:
    result = ValidationResult()
    archive = archive.resolve()
    expected_name = expected_archive_name(release)
    result.check(archive.name == expected_name, f"archive name is {expected_name}", f"archive must be named {expected_name}; got {archive.name}")
    result.check(archive.is_file(), "archive file exists", f"archive does not exist: {archive}")
    if not archive.is_file():
        return result

    with zipfile.ZipFile(archive) as zf:
        raw_names = [name for name in zf.namelist() if name and not name.endswith("/")]
        top_levels = {PurePosixPath(name).parts[0] for name in raw_names if PurePosixPath(name).parts}
        result.check(top_levels == {ROOT_NAME}, f"archive has one fixed root: {ROOT_NAME}/", f"archive top-level entries are {sorted(top_levels)!r}; expected only {ROOT_NAME!r}")

        prefix = f"{ROOT_NAME}/"
        names = {name[len(prefix):] for name in raw_names if name.startswith(prefix)}

        def read_text(name: str) -> str:
            member = prefix + name
            try:
                return zf.read(member).decode("utf-8")
            except KeyError:
                return ""

        validate_common(
            names=names,
            read_text=read_text,
            release=release,
            require_artifacts=require_artifacts,
            result=result,
        )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--source", type=Path, help="unpacked repository root")
    target.add_argument("--archive", type=Path, help="release ZIP archive")
    parser.add_argument("--expected-release", required=True, help="release label in YY.RR form, for example 26.02")
    parser.add_argument("--require-artifacts", action="store_true", help="require current wheel, sdist, checksums, and Libdoc")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not re.fullmatch(r"\d{2}\.\d{2,}", args.expected_release):
        raise SystemExit("--expected-release must use YY.RR form, for example 26.02")
    if args.source is not None:
        result = validate_source(args.source, args.expected_release, args.require_artifacts)
    else:
        result = validate_archive(args.archive, args.expected_release, args.require_artifacts)
    return result.report()


if __name__ == "__main__":
    raise SystemExit(main())
