from __future__ import annotations

import importlib
from collections import defaultdict
from pathlib import Path
from typing import Any

from shapely.geometry import shape

from .errors import ValidationError
from .geojson import FeatureCollection, validate_feature_collection
from .io import read_json

SOURCE_INVENTORY_VERSION = 1
SourceInventoryReport = dict[str, Any]


def _json_value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _geojson_layer_report(
    collection: FeatureCollection,
    *,
    declared_crs: str | None,
    include_bounds: bool,
) -> dict[str, Any]:
    field_types: dict[str, set[str]] = defaultdict(set)
    geometry_types: set[str] = set()
    aggregate_bounds: list[float] | None = None

    for feature in collection["features"]:
        geometry_value = feature["geometry"]
        geometry_types.add(str(geometry_value["type"]))

        properties = feature.get("properties") or {}
        for name, value in properties.items():
            field_types[str(name)].add(_json_value_type(value))

        if include_bounds:
            min_x, min_y, max_x, max_y = shape(geometry_value).bounds
            if aggregate_bounds is None:
                aggregate_bounds = [float(min_x), float(min_y), float(max_x), float(max_y)]
            else:
                aggregate_bounds[0] = min(aggregate_bounds[0], min_x)
                aggregate_bounds[1] = min(aggregate_bounds[1], min_y)
                aggregate_bounds[2] = max(aggregate_bounds[2], max_x)
                aggregate_bounds[3] = max(aggregate_bounds[3], max_y)

    if not geometry_types:
        geometry_type = None
    elif len(geometry_types) == 1:
        geometry_type = next(iter(geometry_types))
    else:
        geometry_type = "Mixed"

    layer: dict[str, Any] = {
        "name": "feature_collection",
        "spatial": True,
        "geometry_type": geometry_type,
        "crs_status": "declared" if declared_crs is not None else "missing",
        "crs": declared_crs,
        "fields": [
            {"name": name, "types": sorted(types)}
            for name, types in sorted(field_types.items())
        ],
        "feature_count_status": "known",
        "feature_count": len(collection["features"]),
    }
    if include_bounds:
        layer["bounds"] = aggregate_bounds
    return layer


def inventory_geojson(
    collection: FeatureCollection,
    *,
    include_bounds: bool = False,
) -> SourceInventoryReport:
    """Summarize one GeoJSON FeatureCollection without exposing attribute values.

    GeoJSON parsing necessarily loads its feature rows, so its feature count is always known. Bounds
    remain opt-in because they require geometry traversal and can expose the source extent.
    """
    validated = validate_feature_collection(collection)
    declared_crs = validated.get("starshine:crs")
    if not isinstance(declared_crs, str) or not declared_crs.strip():
        declared_crs = None

    return {
        "schema_version": SOURCE_INVENTORY_VERSION,
        "source_format": "geojson",
        "layer_count": 1,
        "bounds_requested": include_bounds,
        "feature_count_forced": False,
        "layers": [
            _geojson_layer_report(
                validated,
                declared_crs=declared_crs,
                include_bounds=include_bounds,
            )
        ],
    }


def _require_pyogrio() -> Any:
    try:
        return importlib.import_module("pyogrio")
    except ImportError as exc:
        raise ValidationError(
            'GeoPackage inventory requires optional dependencies; install "starshine-geo[geopackage]"'
        ) from exc


def _normalize_rows(rows: Any) -> list[list[Any]]:
    if hasattr(rows, "tolist"):
        rows = rows.tolist()
    return [list(row) if isinstance(row, (list, tuple)) else [row] for row in rows]


def _normalize_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if hasattr(value, "tolist"):
        value = value.tolist()
    return list(value)


def _geopackage_layer_report(
    pyogrio: Any,
    package: Path,
    layer_name: str,
    geometry_hint: Any,
    *,
    force_feature_count: bool,
    include_bounds: bool,
) -> dict[str, Any]:
    info = pyogrio.read_info(
        str(package),
        layer=layer_name,
        force_feature_count=force_feature_count,
        force_total_bounds=include_bounds,
    )

    geometry_type = info.get("geometry_type")
    if geometry_type is None and geometry_hint not in (None, "None", ""):
        geometry_type = str(geometry_hint)
    spatial = geometry_type not in (None, "None", "")

    crs = info.get("crs") if spatial else None
    if spatial:
        crs_status = "declared" if isinstance(crs, str) and crs.strip() else "missing"
        if crs_status == "missing":
            crs = None
    else:
        crs_status = "not_applicable"

    fields = _normalize_sequence(info.get("fields"))
    dtypes = _normalize_sequence(info.get("dtypes"))
    field_schema = [
        {
            "name": str(name),
            "type": str(dtypes[index]) if index < len(dtypes) else "unknown",
        }
        for index, name in enumerate(fields)
    ]

    raw_count = info.get("features", -1)
    count_known = isinstance(raw_count, int) and raw_count >= 0
    report: dict[str, Any] = {
        "name": layer_name,
        "spatial": spatial,
        "geometry_type": None if not spatial else str(geometry_type),
        "crs_status": crs_status,
        "crs": crs,
        "fields": field_schema,
        "feature_count_status": "known" if count_known else "unknown",
        "feature_count": raw_count if count_known else None,
    }
    if include_bounds:
        raw_bounds = info.get("total_bounds")
        if raw_bounds is None:
            report["bounds"] = None
        else:
            report["bounds"] = [float(value) for value in _normalize_sequence(raw_bounds)]
    return report


def inventory_geopackage(
    path: str | Path,
    *,
    force_feature_count: bool = False,
    include_bounds: bool = False,
) -> SourceInventoryReport:
    """Inventory GeoPackage layers using metadata APIs without loading feature rows by default."""
    package = Path(path)
    if package.suffix.casefold() != ".gpkg":
        raise ValidationError("GeoPackage inventory requires a .gpkg source")
    if not package.is_file():
        raise ValidationError(f"GeoPackage not found: {package}")

    pyogrio = _require_pyogrio()
    rows = _normalize_rows(pyogrio.list_layers(str(package)))
    if not rows:
        raise ValidationError("GeoPackage contains no readable layers")

    layers: list[dict[str, Any]] = []
    for row in rows:
        layer_name = str(row[0])
        geometry_hint = row[1] if len(row) > 1 else None
        layers.append(
            _geopackage_layer_report(
                pyogrio,
                package,
                layer_name,
                geometry_hint,
                force_feature_count=force_feature_count,
                include_bounds=include_bounds,
            )
        )

    return {
        "schema_version": SOURCE_INVENTORY_VERSION,
        "source_format": "geopackage",
        "layer_count": len(layers),
        "bounds_requested": include_bounds,
        "feature_count_forced": force_feature_count,
        "layers": layers,
    }


def inventory_source(
    path: str | Path,
    *,
    force_feature_count: bool = False,
    include_bounds: bool = False,
) -> SourceInventoryReport:
    """Inventory a GeoJSON or GeoPackage source without including paths or attribute values."""
    source = Path(path)
    suffix = source.suffix.casefold()
    if suffix == ".gpkg":
        return inventory_geopackage(
            source,
            force_feature_count=force_feature_count,
            include_bounds=include_bounds,
        )
    if suffix in {".geojson", ".json"}:
        return inventory_geojson(read_json(source), include_bounds=include_bounds)
    raise ValidationError("inventory supports GeoJSON (.geojson/.json) and GeoPackage (.gpkg) sources")


def render_source_inventory_markdown(report: SourceInventoryReport) -> str:
    """Render a privacy-aware inventory report without reconstructing source values."""
    lines = [
        "# Starshine Source Inventory",
        "",
        f"- Format: `{report['source_format']}`",
        f"- Layers: {report['layer_count']}",
        f"- Forced feature count: {'yes' if report['feature_count_forced'] else 'no'}",
        f"- Bounds requested: {'yes' if report['bounds_requested'] else 'no'}",
        "",
    ]

    for layer in report["layers"]:
        lines.extend(
            [
                f"## Layer `{layer['name']}`",
                "",
                f"- Spatial: {'yes' if layer['spatial'] else 'no'}",
                f"- Geometry type: `{layer['geometry_type']}`" if layer["geometry_type"] else "- Geometry type: n/a",
                f"- CRS status: `{layer['crs_status']}`",
                f"- CRS: `{layer['crs']}`" if layer["crs"] else "- CRS: n/a",
                f"- Feature count status: `{layer['feature_count_status']}`",
                (
                    f"- Feature count: {layer['feature_count']}"
                    if layer["feature_count"] is not None
                    else "- Feature count: unknown"
                ),
            ]
        )
        if "bounds" in layer:
            lines.append(f"- Bounds: `{layer['bounds']}`" if layer["bounds"] is not None else "- Bounds: unavailable")
        lines.extend(["", "### Fields", ""])
        if not layer["fields"]:
            lines.append("No fields reported.")
        else:
            for field in layer["fields"]:
                if "types" in field:
                    field_type = ", ".join(field["types"])
                else:
                    field_type = field.get("type", "unknown")
                lines.append(f"- `{field['name']}`: `{field_type}`")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "SOURCE_INVENTORY_VERSION",
    "SourceInventoryReport",
    "inventory_geojson",
    "inventory_geopackage",
    "inventory_source",
    "render_source_inventory_markdown",
]
