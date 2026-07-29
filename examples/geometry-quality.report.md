# Starshine Geometry Quality Report

- Status: **FAIL**
- Features: 5
- Parsed geometries: 5
- Valid geometries: 3
- Invalid geometry entries: 2
- Errors: 2
- Warnings: 3
- Declared CRS: `null`
- CRS status: missing

## Geometry structure

- `LineString`: 1
- `Point`: 2
- `Polygon`: 2
- Total coordinate positions: 9
- Maximum coordinate positions in one feature: 5
- Duplicate geometry groups: 1
- Features in duplicate groups: 2

## Coordinate dimensions

- 2D: 3
- 3D: 1
- mixed: 0
- unsupported: 0
- unknown: 1

## Findings

- **WARNING** `missing_declared_crs`: The collection does not declare starshine:crs. Count: 1
- **ERROR** `topologically_invalid_geometry` (`Polygon`): A geometry is topologically invalid: Self-intersection. Count: 1; sample feature indexes: [2]
- **ERROR** `empty_geometry` (`Polygon`): A geometry is empty. Count: 1; sample feature indexes: [3]
- **WARNING** `duplicate_geometry` (`Point`): Multiple features share an identical normalized geometry. Count: 2; sample feature indexes: [0, 1]

## Evidence

- Collection digest status: available
- Collection digest: `sha256:8f889db5a3012df32f80fdec07ed0ce4ea57ea1c501f00b9f14e8c7754e1d9b7`
- Quality digest: `sha256:c7a1eb1884b58eaf73d79ce2da823f1bf35029bf267970e84306f10356c32765`
