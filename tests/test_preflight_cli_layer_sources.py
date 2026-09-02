from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from starshine_geo import preflight_workflow_inputs
from starshine_geo._cli_layer_sources import prepare_layer_bindings
from starshine_geo.cli import main
from starshine_geo.errors import StarshineError, ValidationError

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "starshine_geo"
WORKFLOW_PATH = ROOT / "examples" / "plan.workflow.json"
SOURCE_PATH = ROOT / "examples" / "data" / "clip-source.geojson"
MASK_PATH = ROOT / "examples" / "data" / "clip-mask.geojson"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_mixed_sources_load_after_all_names_are_validated(monkeypatch, tmp_path):
    geojson_path = tmp_path / "source.geojson"
    package_path = tmp_path / "mask.gpkg"
    expected_source = _load(SOURCE_PATH)
    expected_mask = _load(MASK_PATH)
    calls: list[tuple[str, Path, str | None]] = []

    def fake_geojson(path: Path):
        calls.append(("geojson", path, None))
        return expected_source

    def fake_geopackage(path: Path, layer: str):
        calls.append(("geopackage", path, layer))
        return expected_mask

    monkeypatch.setattr("starshine_geo._cli_layer_sources._read_geojson_source", fake_geojson)
    monkeypatch.setattr(
        "starshine_geo._cli_layer_sources._read_geopackage_source", fake_geopackage
    )

    bindings = prepare_layer_bindings(
        [f"source={geojson_path}"],
        [["mask", str(package_path), "analysis_mask"]],
    )
    assert calls == []
    layers = bindings.load()

    assert layers == {"source": expected_source, "mask": expected_mask}
    assert bindings.paths == {"source": geojson_path, "mask": package_path}
    assert calls == [
        ("geojson", geojson_path, None),
        ("geopackage", package_path, "analysis_mask"),
    ]


def test_duplicate_names_across_formats_are_rejected_before_any_read(monkeypatch):
    monkeypatch.setattr(
        "starshine_geo._cli_layer_sources._read_geojson_source",
        lambda path: pytest.fail("GeoJSON I/O must not start before name validation"),
    )
    monkeypatch.setattr(
        "starshine_geo._cli_layer_sources._read_geopackage_source",
        lambda path, layer: pytest.fail("GeoPackage I/O must not start before name validation"),
    )

    with pytest.raises(StarshineError, match="duplicate layer name"):
        prepare_layer_bindings(
            ["source=source.geojson"],
            [["source", "source.gpkg", "sites"]],
        )


def test_geopackage_binding_requires_explicit_nonempty_selection(monkeypatch):
    monkeypatch.setattr(
        "starshine_geo._cli_layer_sources._read_geopackage_source",
        lambda path, layer: pytest.fail("invalid bindings must not be read"),
    )

    with pytest.raises(StarshineError, match="selection must be non-empty"):
        prepare_layer_bindings([], [["source", "source.gpkg", "  "]])


def test_optional_backend_error_is_preserved_by_cli_adapter(monkeypatch):
    def missing_backend(path: Path, layer: str):
        raise ValidationError(
            'GeoPackage support requires optional dependencies; install "starshine-geo[geopackage]"'
        )

    monkeypatch.setattr(
        "starshine_geo._cli_layer_sources._read_geopackage_source", missing_backend
    )
    bindings = prepare_layer_bindings([], [["source", "source.gpkg", "sites"]])
    with pytest.raises(ValidationError, match=r"starshine-geo\[geopackage\]"):
        bindings.load()


def test_preflight_cli_mixed_sources_matches_direct_public_api(monkeypatch, capsys):
    source = _load(SOURCE_PATH)
    mask = _load(MASK_PATH)
    monkeypatch.setattr(
        "starshine_geo._cli_layer_sources._read_geopackage_source",
        lambda path, layer: mask,
    )

    result = main(
        [
            "preflight",
            str(WORKFLOW_PATH),
            "--layer",
            f"source={SOURCE_PATH}",
            "--gpkg-layer",
            "mask",
            "synthetic.gpkg",
            "mask",
            "--format",
            "json",
        ]
    )

    assert result == 0
    assert json.loads(capsys.readouterr().out) == preflight_workflow_inputs(
        _load(WORKFLOW_PATH), {"source": source, "mask": mask}
    )


def test_preflight_output_guard_covers_geopackage_artifact(monkeypatch, tmp_path, capsys):
    package = tmp_path / "inputs.gpkg"
    monkeypatch.setattr(
        "starshine_geo._cli_layer_sources._read_geopackage_source",
        lambda path, layer: pytest.fail("overwrite guards must run before GeoPackage I/O"),
    )

    result = main(
        [
            "preflight",
            str(WORKFLOW_PATH),
            "--gpkg-layer",
            "source",
            str(package),
            "source",
            "--gpkg-layer",
            "mask",
            str(package),
            "mask",
            "--output",
            str(package),
        ]
    )

    assert result == 2
    assert "must not overwrite an input layer" in capsys.readouterr().err


def test_preflight_sarif_path_guard_runs_before_geopackage_io(monkeypatch, tmp_path, capsys):
    root = tmp_path / "root"
    root.mkdir()
    workflow = root / "workflow.json"
    workflow.write_text(WORKFLOW_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    outside = tmp_path / "outside.gpkg"
    monkeypatch.setattr(
        "starshine_geo._cli_layer_sources._read_geopackage_source",
        lambda path, layer: pytest.fail("SARIF containment must be checked before GeoPackage I/O"),
    )

    result = main(
        [
            "preflight",
            str(workflow),
            "--gpkg-layer",
            "source",
            str(outside),
            "source",
            "--format",
            "sarif",
            "--sarif-root",
            str(root),
        ]
    )

    assert result == 2
    assert "contained by --sarif-root" in capsys.readouterr().err


def _relative_imports(module_name: str) -> set[str]:
    path = PACKAGE_ROOT / f"{module_name}.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module
    }


def test_cli_adapter_and_core_preflight_import_boundaries_are_one_way():
    adapter_imports = _relative_imports("_cli_layer_sources")
    assert adapter_imports == {"errors", "geojson", "geopackage", "io"}
    assert "preflight" not in adapter_imports

    for module in (
        "preflight",
        "_preflight_checks",
        "_preflight_findings",
        "_preflight_model",
        "_preflight_render",
        "_preflight_report",
        "preflight_sarif",
    ):
        imports = _relative_imports(module)
        assert "_cli_layer_sources" not in imports
        assert "geopackage" not in imports
