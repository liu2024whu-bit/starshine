from __future__ import annotations

import argparse
import re
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
_PACKAGE_SOURCE_ROOT = Path("src")


def _project_version() -> str:
    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    return str(metadata["project"]["version"])


def _latest_release_version() -> str:
    citation = Path("CITATION.cff").read_text(encoding="utf-8")
    match = re.search(r"^version:\s*(\S+)\s*$", citation, re.MULTILINE)
    if match is None:
        raise RuntimeError("CITATION.cff is missing version")
    return match.group(1)


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


def _package_python_suffixes(source_root: Path = _PACKAGE_SOURCE_ROOT) -> tuple[str, ...]:
    if not source_root.is_dir():
        raise RuntimeError(f"package source directory does not exist: {source_root}")
    suffixes = tuple(
        sorted(
            path.relative_to(source_root).as_posix()
            for path in source_root.rglob("*.py")
            if path.is_file()
        )
    )
    if not suffixes:
        raise RuntimeError(f"source directory contains no Python modules: {source_root}")
    return suffixes


def _sdist_package_suffixes(source_root: Path = _PACKAGE_SOURCE_ROOT) -> tuple[str, ...]:
    return tuple(f"/src/{suffix}" for suffix in _package_python_suffixes(source_root))


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
                *_package_python_suffixes(),
                "starshine_server/static/index.html",
                "starshine_server/static/styles.css",
                "starshine_server/static/app.js",
                "starshine_server/static/api.js",
                "starshine_server/static/assurance.js",
                "starshine_server/static/editor.js",
                "starshine_server/static/render.js",
                ".dist-info/METADATA",
            ),
            path.name,
        )
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = archive.read(metadata_name).decode("utf-8")
        if f"Version: {version}\n" not in metadata:
            raise RuntimeError(f"wheel metadata does not declare version {version}")


def _check_sdist(path: Path, version: str, release_version: str) -> None:
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
                "/requirements/ci-validation.txt",
                "/README.md",
                "/LICENSE",
                "/benchmarks/corpus.py",
                "/benchmarks/run.py",
                "/benchmarks/spatial_index.py",
                "/docs/README.md",
                "/docs/ARCHITECTURE.md",
                "/docs/BENCHMARKS.md",
                "/docs/CLIP.md",
                "/docs/INTERSECTION.md",
                "/docs/GEOMETRY_QUALITY.md",
                "/docs/INSPECTION.md",
                "/docs/REPRODUCING.md",
                "/docs/PLATFORM.md",
                "/docs/PRODUCT.md",
                "/docs/VECTOR_QUALITY_GATE.md",
                "/docs/GEOMETRY_METRICS.md",
                "/docs/WORKFLOW_CONTRACTS.md",
                "/docs/WORKFLOW_EXPLAIN.md",
                "/docs/WORKFLOW_GRAPH.md",
                "/docs/NEAREST.md",
                "/docs/SPATIAL_JOIN.md",
                "/docs/SPATIAL_INDEXING.md",
                "/docs/OPERATORS.md",
                "/docs/TEACHING_FAILURES.md",
                "/docs/WORKFLOW_PLANNING.md",
                "/docs/WORKFLOW_PREFLIGHT.md",
                "/docs/WORKFLOW_PREFLIGHT_SARIF.md",
                "/examples/teaching/geographic-points.geojson",
                "/examples/teaching/buffer-geographic-invalid.workflow.json",
                "/examples/teaching/projected-points.geojson",
                "/examples/teaching/projected-points.inspection.json",
                "/examples/teaching/buffer-projected-valid.workflow.json",
                "/examples/teaching/self-intersecting-polygon.geojson",
                "/examples/teaching/empty-polygon.geojson",
                "/examples/teaching/malformed-properties.geojson",
                "/schemas/benchmark-report-v1.schema.json",
                "/schemas/doctor-report-v1.schema.json",
                "/schemas/reproduction-report-v1.schema.json",
                "/schemas/spatial-index-benchmark-v1.schema.json",
                "/schemas/geometry-quality-report-v1.schema.json",
                "/schemas/inspection-report-v1.schema.json",
                "/schemas/source-inventory-v1.schema.json",
                "/schemas/operator-catalog-v1.schema.json",
                "/schemas/workflow-contract-v1.schema.json",
                "/schemas/workflow-explanation-v1.schema.json",
                "/schemas/workflow-graph-v1.schema.json",
                "/schemas/workflow-plan-v1.schema.json",
                "/schemas/workflow-preflight-v1.schema.json",
                "/schemas/workflow-v1.schema.json",
                *_sdist_package_suffixes(),
                "/src/starshine_server/static/index.html",
                "/src/starshine_server/static/styles.css",
                "/src/starshine_server/static/app.js",
                "/src/starshine_server/static/api.js",
                "/src/starshine_server/static/assurance.js",
                "/src/starshine_server/static/editor.js",
                "/src/starshine_server/static/render.js",
                "/tests/test_doctor.py",
                "/tests/test_geometry_quality.py",
                "/tests/test_geometry_quality_architecture.py",
                "/tests/test_inventory.py",
                "/tests/test_geopackage_preflight_cli.py",
                "/tests/test_geopackage_run_cli.py",
                "/tests/test_cli_run_io_architecture.py",
                "/tests/test_preflight_architecture.py",
                "/tests/test_preflight_cli_layer_sources.py",
                "/tests/test_spatial_index.py",
                "/tests/test_clip.py",
                "/tests/test_intersection.py",
                "/tests/test_spatial_index_architecture.py",
                "/tests/test_spatial_index_benchmark.py",
                "/tests/test_reproduction_harness.py",
                "/scripts/check_release_readiness.py",
                "/scripts/check_reproduction_report.py",
                "/scripts/check_spatial_index_benchmark.py",
                "/scripts/smoke_installed_wheel.py",
                "/scripts/smoke_installed_preflight_sarif.py",
                "/scripts/smoke_installed_geometry_quality.py",
                "/scripts/smoke_installed_geopackage.py",
                "/scripts/smoke_installed_server.py",
                "/scripts/reproduce_installed_core.py",
                "/scripts/independent_reproduction.py",
                "/scripts/refresh_public_evidence.py",
                "/scripts/verify_teaching_examples.py",
                "/examples/geometry-quality.geojson",
                "/examples/geometry-quality.report.json",
                "/examples/geometry-quality.report.md",
                "/examples/reproject.workflow.json",
                "/examples/clip.workflow.json",
                "/examples/intersection.workflow.json",
                "/examples/geometry-metrics.workflow.json",
                "/examples/nearest.workflow.json",
                "/examples/spatial-join.workflow.json",
                "/examples/plan.workflow.json",
                "/examples/plan.workflow.contract.md",
                "/examples/plan.workflow.explanation.md",
                "/examples/plan.workflow.preflight.md",
                "/examples/plan.workflow.preflight.sarif",
                "/examples/plan.workflow.mmd",
                "/examples/data/clip-source.geojson",
                "/examples/data/clip-mask.geojson",
                "/examples/data/intersection-parcels.geojson",
                "/examples/data/intersection-zones.geojson",
                "/examples/data/metric-features.geojson",
                "/examples/data/nearest-source.geojson",
                "/examples/data/nearest-candidates.geojson",
                "/examples/data/join-points.geojson",
                "/examples/data/join-polygons.geojson",
                f"/docs/releases/{release_version}.md",
            ),
            path.name,
        )


def check(dist_dir: Path) -> None:
    version = _project_version()
    release_version = _latest_release_version()
    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise RuntimeError(
            f"expected exactly one wheel and one sdist, found {len(wheels)} and {len(sdists)}"
        )
    _check_wheel(wheels[0], version)
    _check_sdist(sdists[0], version, release_version)
    print(
        "Distribution artifacts passed inspection for "
        f"Starshine Geo {version}; latest stable metadata is {release_version}."
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dist_dir", type=Path, nargs="?", default=Path("dist"))
    args = parser.parse_args()
    check(args.dist_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
