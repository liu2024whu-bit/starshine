from __future__ import annotations

import argparse
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised only on Python 3.10
    import tomli as tomllib

_MAX_MEMBER_BYTES = 5 * 1024 * 1024
_FORBIDDEN_MEMBER_PARTS = {
    ".env",
    ".git",
    ".pytest_cache",
    "__pycache__",
    "archive",
    "ocr",
    "runtime_outputs",
}


def _project_version() -> str:
    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    return str(metadata["project"]["version"])


def _validate_member_names(members: list[tuple[str, int]], archive_name: str) -> None:
    for name, size in members:
        path = PurePosixPath(name)
        if path.is_absolute() or "\\" in name:
            raise RuntimeError(f"unsafe archive member path in {archive_name}: {name}")
        if set(path.parts) & _FORBIDDEN_MEMBER_PARTS:
            raise RuntimeError(f"forbidden archive member in {archive_name}: {name}")
        if size > _MAX_MEMBER_BYTES:
            raise RuntimeError(
                f"archive member exceeds 5 MiB in {archive_name}: {name} ({size} bytes)"
            )


def _require_suffixes(names: list[str], suffixes: tuple[str, ...], archive_name: str) -> None:
    missing = [suffix for suffix in suffixes if not any(name.endswith(suffix) for name in names)]
    if missing:
        raise RuntimeError(f"{archive_name} is missing expected files: {missing}")


def _check_wheel(path: Path, version: str) -> None:
    if f"-{version}-" not in path.name:
        raise RuntimeError(f"wheel filename does not contain version {version}: {path.name}")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        members = [(info.filename, info.file_size) for info in infos]
        names = [name for name, _ in members]
        _validate_member_names(members, path.name)
        _require_suffixes(
            names,
            (
                "starshine_geo/__init__.py",
                "starshine_geo/_version.py",
                "starshine_geo/cli.py",
                "starshine_geo/inspection.py",
                ".dist-info/METADATA",
            ),
            path.name,
        )
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = archive.read(metadata_name).decode("utf-8")
        if f"Version: {version}\n" not in metadata:
            raise RuntimeError(f"wheel metadata does not declare version {version}")


def _check_sdist(path: Path, version: str) -> None:
    if f"-{version}.tar.gz" not in path.name:
        raise RuntimeError(f"sdist filename does not contain version {version}: {path.name}")
    with tarfile.open(path, mode="r:gz") as archive:
        infos = archive.getmembers()
        members = [(info.name, info.size) for info in infos if info.isfile()]
        names = [name for name, _ in members]
        _validate_member_names(members, path.name)
        _require_suffixes(
            names,
            (
                "/pyproject.toml",
                "/README.md",
                "/LICENSE",
                "/benchmarks/corpus.py",
                "/benchmarks/run.py",
                "/docs/BENCHMARKS.md",
                "/docs/INSPECTION.md",
                "/schemas/benchmark-report-v1.schema.json",
                "/schemas/inspection-report-v1.schema.json",
                "/schemas/workflow-v1.schema.json",
                "/scripts/smoke_installed_wheel.py",
                "/docs/releases/0.2.0.md",
            ),
            path.name,
        )


def check(dist_dir: Path) -> None:
    version = _project_version()
    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise RuntimeError(
            f"expected exactly one wheel and one sdist, found {len(wheels)} and {len(sdists)}"
        )
    _check_wheel(wheels[0], version)
    _check_sdist(sdists[0], version)
    print(f"Release artifacts passed inspection for Starshine Geo {version}.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dist_dir", type=Path, nargs="?", default=Path("dist"))
    args = parser.parse_args()
    check(args.dist_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
