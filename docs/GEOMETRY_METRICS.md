# Projected geometry metrics

`calculate_geometry_metrics()` and the `geometry_metrics` workflow operation attach area and length
values to every feature without changing geometry, source properties, CRS, or feature order.

```python
from starshine_geo import calculate_geometry_metrics

measured = calculate_geometry_metrics(
    collection,
    area_field="area_m2",
    length_field="length_m",
)
```

```bash
starshine run examples/geometry-metrics.workflow.json \
  --layer features=examples/data/metric-features.geojson \
  --output-layer measured \
  --output examples/output/measured-features.geojson
```

## Contract

- the input must be a valid `FeatureCollection` with an explicit projected `starshine:crs`;
- values use that projected CRS's squared and linear units;
- polygon length includes exterior and interior-ring boundaries;
- Point and LineString area follows the geometry model and is `0.0`;
- Point length is `0.0`;
- output field names must be non-empty, distinct, and absent from every source property object;
- all input geometry, properties, order, and CRS are preserved;
- Starshine performs no hidden reprojection, unit conversion, rounding, or geometry repair.

The operation is deliberately limited to raw geometric measurements. Unit labels, geodesic metrics,
centroids, compactness indices, and derived domain statistics belong in separate reviewed operators
rather than an expanding all-purpose function.
