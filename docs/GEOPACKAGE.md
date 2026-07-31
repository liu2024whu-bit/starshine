# GeoPackage adapter contract

GeoPackage support is optional and does not change Starshine's canonical in-memory format. The
workflow engine continues to receive validated GeoJSON `FeatureCollection` objects with an
explicit `starshine:crs` member.

## Install the optional adapter

```bash
python -m pip install -e ".[geopackage]"
```

The extra installs GeoPandas and Pyogrio. Importing `starshine_geo` and running GeoJSON workflows
do not require either package; the adapter loads them only when a GeoPackage function is called.

## Read a layer

```python
from starshine_geo import read_geopackage

roads = read_geopackage("study.gpkg", layer="roads")
```

Rules:

- a package with multiple vector layers requires an explicit `layer`;
- a single-layer package may omit `layer`;
- the selected layer must exist and declare a valid CRS;
- the CRS is normalized and preserved as `starshine:crs`;
- returned data passes the same GeoJSON geometry validation as other Starshine inputs.

Use `list_geopackage_layers("study.gpkg")` to inspect layer names without loading feature rows.

## Use selected layers in Workflow Preflight

The CLI can adapt explicitly selected GeoPackage layers into the unchanged in-memory Preflight API:

```bash
starshine preflight workflow.json \
  --gpkg-layer roads study.gpkg road_centerlines \
  --geopackage-layer zones study.gpkg planning_zones
```

Each binding uses `NAME PATH LAYER`:

- `NAME` is the logical external layer referenced by Workflow v1;
- `PATH` is the containing `.gpkg` artifact;
- `LAYER` is the exact vector layer to read.

Selection is intentionally mandatory even when a package currently contains one layer. This keeps
a reviewed command stable if another layer is later added to the same container. GeoJSON
`--layer NAME=PATH` bindings and GeoPackage bindings may be mixed. Duplicate logical names across
formats are rejected before any source is read or optional backend is loaded.

The CLI validates output and SARIF paths before feature I/O. An output cannot overwrite a package
source. SARIF points to the repository-relative `.gpkg` container; logical locations still identify
the Workflow layer name. Multiple logical inputs may select different vector layers from the same
package without modifying it.

The Python `preflight_workflow_inputs()` function remains FeatureCollection-only. GeoPandas,
Pyogrio, GDAL, and package paths therefore remain outside the Preflight dependency graph.

## Write a layer

```python
from starshine_geo import write_geopackage

write_geopackage(
    result,
    "result.gpkg",
    layer="analysis_result",
    input_paths=["study.gpkg"],
)
```

Rules:

- the output layer name must be explicit;
- the FeatureCollection must contain at least one feature and a valid `starshine:crs`;
- an existing destination is rejected unless `overwrite=True` is supplied;
- writing over a declared input path is rejected unless `overwrite=True` is supplied;
- parent directories may be created, but no second workflow engine or private database access is
  introduced.

## Validation coverage

The base CI matrix runs on Python 3.10, 3.11, and 3.12 without installing the optional GIS stack.
It verifies lazy dependency loading, explicit layer selection, CRS validation, invalid layer
handling, and overwrite guards.

A dedicated Python 3.11 GeoPackage job installs `.[dev,geopackage]` and uses self-created features to
perform real write, layer-list, read, CRS, geometry, property, explicit-overwrite, multi-layer
Preflight, mixed-source, and SARIF checks. Separate clean Python 3.10, 3.11, and 3.12 jobs install the
exact CI-built wheel with its `geopackage` extra and run the installed console command against a
self-created multi-layer package. No private dataset, external service, database credential, or
checked-in binary fixture is required.
