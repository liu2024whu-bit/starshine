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

## Current validation scope

The first adapter PR tests dependency isolation, explicit layer selection, CRS preservation,
invalid layer handling, and overwrite guards without installing the optional GIS stack in the
base CI matrix. A follow-up change will add self-created GeoPackage fixtures and real round-trip
tests in an optional-dependency CI job before Issue #2 is considered complete.
