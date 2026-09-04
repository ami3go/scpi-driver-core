"""Create and verify the standard RF Keysight N6700 release archive."""
from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path

from verify_project_package import (
    ROOT_NAME,
    expected_archive_name,
    parse_project_version,
    release_from_python_version,
    validate_archive,
    validate_source,
)

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "site",
    "build",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wheel_distribution_version(version: str) -> str:
    if re.fullmatch(r"\d+\.\d+\.\d+", version) is None:
        raise ValueError(f"Unsupported package version: {version!r}")
    return version


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    if repo.name != ROOT_NAME:
        raise SystemExit(f"Repository folder must be exactly {ROOT_NAME!r}; got {repo.name!r}")

    version = parse_project_version((repo / "pyproject.toml").read_text(encoding="utf-8"))
    release = release_from_python_version(version)
    archive_name = expected_archive_name(release)
    normalized_version = wheel_distribution_version(version)

    artifact_paths = [
        repo / "dist" / f"robotframework_keysight_n6700-{normalized_version}-py3-none-any.whl",
        repo / "dist" / f"robotframework_keysight_n6700-{normalized_version}.tar.gz",
        repo / "docs" / "KeysightN6700Library.html",
    ]
    missing = [str(path.relative_to(repo)) for path in artifact_paths if not path.is_file()]
    if missing:
        raise SystemExit("Missing build artifacts: " + ", ".join(missing))

    source_result = validate_source(repo, release, require_artifacts=True)
    if source_result.errors:
        source_result.report()
        raise SystemExit("Source package validation failed")

    checksum_file = repo / "SHA256SUMS.txt"
    checksum_file.write_text(
        "".join(f"{sha256(path)}  {path.relative_to(repo).as_posix()}\n" for path in artifact_paths),
        encoding="utf-8",
    )

    archive = repo.parent / archive_name
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(repo.rglob("*")):
            relative = path.relative_to(repo)
            if any(part in EXCLUDED_DIRS for part in relative.parts):
                continue
            if path.suffix in EXCLUDED_SUFFIXES:
                continue
            arcname = Path(ROOT_NAME) / relative
            if path.is_dir():
                zf.writestr(arcname.as_posix().rstrip("/") + "/", b"")
            else:
                zf.write(path, arcname.as_posix())

    archive_result = validate_archive(archive, release, require_artifacts=True)
    if archive_result.errors:
        archive_result.report()
        archive.unlink(missing_ok=True)
        raise SystemExit("Release archive validation failed")

    archive_hash = sha256(archive)
    (archive.with_suffix(archive.suffix + ".sha256")).write_text(
        f"{archive_hash}  {archive.name}\n", encoding="utf-8"
    )
    print(f"Created {archive}")
    print(f"SHA256 {archive_hash}")


if __name__ == "__main__":
    main()
