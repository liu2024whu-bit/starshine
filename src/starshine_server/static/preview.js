function finitePoint(value) {
  if (
    !Array.isArray(value) ||
    value.length < 2 ||
    typeof value[0] !== "number" ||
    typeof value[1] !== "number" ||
    !Number.isFinite(value[0]) ||
    !Number.isFinite(value[1])
  ) {
    return null;
  }
  return [value[0], value[1]];
}

function pointSeries(values, minimumLength) {
  if (!Array.isArray(values)) {
    return null;
  }
  const points = values.map(finitePoint).filter((value) => value !== null);
  return points.length >= minimumLength ? points : null;
}

function collectGeometry(geometry, primitives) {
  if (!geometry || typeof geometry !== "object") {
    return;
  }

  const type = geometry.type;
  const coordinates = geometry.coordinates;

  if (type === "Point") {
    const point = finitePoint(coordinates);
    if (point) {
      primitives.push({ kind: "point", points: [point] });
    }
    return;
  }

  if (type === "MultiPoint") {
    if (Array.isArray(coordinates)) {
      for (const value of coordinates) {
        const point = finitePoint(value);
        if (point) {
          primitives.push({ kind: "point", points: [point] });
        }
      }
    }
    return;
  }

  if (type === "LineString") {
    const line = pointSeries(coordinates, 2);
    if (line) {
      primitives.push({ kind: "line", points: line });
    }
    return;
  }

  if (type === "MultiLineString") {
    if (Array.isArray(coordinates)) {
      for (const value of coordinates) {
        const line = pointSeries(value, 2);
        if (line) {
          primitives.push({ kind: "line", points: line });
        }
      }
    }
    return;
  }

  if (type === "Polygon") {
    if (Array.isArray(coordinates)) {
      for (const value of coordinates) {
        const ring = pointSeries(value, 3);
        if (ring) {
          primitives.push({ kind: "ring", points: ring });
        }
      }
    }
    return;
  }

  if (type === "MultiPolygon") {
    if (Array.isArray(coordinates)) {
      for (const polygon of coordinates) {
        if (!Array.isArray(polygon)) {
          continue;
        }
        for (const value of polygon) {
          const ring = pointSeries(value, 3);
          if (ring) {
            primitives.push({ kind: "ring", points: ring });
          }
        }
      }
    }
    return;
  }

  if (type === "GeometryCollection" && Array.isArray(geometry.geometries)) {
    for (const child of geometry.geometries) {
      collectGeometry(child, primitives);
    }
  }
}

function rawPrimitives(result) {
  const primitives = [];
  const features = result && Array.isArray(result.features) ? result.features : [];
  for (const feature of features) {
    if (feature && typeof feature === "object") {
      collectGeometry(feature.geometry, primitives);
    }
  }
  return primitives;
}

function boundsFor(primitives) {
  const points = primitives.flatMap((primitive) => primitive.points);
  if (points.length === 0) {
    return null;
  }

  let minX = points[0][0];
  let maxX = points[0][0];
  let minY = points[0][1];
  let maxY = points[0][1];

  for (const [x, y] of points.slice(1)) {
    minX = Math.min(minX, x);
    maxX = Math.max(maxX, x);
    minY = Math.min(minY, y);
    maxY = Math.max(maxY, y);
  }
  return { min_x: minX, min_y: minY, max_x: maxX, max_y: maxY };
}

function mapper(bounds, width, height, padding) {
  const drawableWidth = Math.max(1, width - 2 * padding);
  const drawableHeight = Math.max(1, height - 2 * padding);
  const spanX = bounds.max_x - bounds.min_x;
  const spanY = bounds.max_y - bounds.min_y;

  const scaleX = spanX > 0 ? drawableWidth / spanX : Number.POSITIVE_INFINITY;
  const scaleY = spanY > 0 ? drawableHeight / spanY : Number.POSITIVE_INFINITY;
  let scale = Math.min(scaleX, scaleY);
  if (!Number.isFinite(scale)) {
    scale = Number.isFinite(scaleX) ? scaleX : Number.isFinite(scaleY) ? scaleY : 1;
  }

  const usedWidth = spanX * scale;
  const usedHeight = spanY * scale;
  const offsetX = (width - usedWidth) / 2;
  const offsetY = (height - usedHeight) / 2;

  return ([x, y]) => [
    offsetX + (x - bounds.min_x) * scale,
    height - (offsetY + (y - bounds.min_y) * scale),
  ];
}

export function buildResultPreview(
  result,
  { width = 760, height = 440, padding = 28 } = {},
) {
  const primitives = rawPrimitives(result);
  const bounds = boundsFor(primitives);

  if (!bounds) {
    return {
      width,
      height,
      bounds: null,
      coordinate_count: 0,
      primitive_count: 0,
      primitives: [],
    };
  }

  const mapPoint = mapper(bounds, width, height, padding);
  return {
    width,
    height,
    bounds,
    coordinate_count: primitives.reduce(
      (total, primitive) => total + primitive.points.length,
      0,
    ),
    primitive_count: primitives.length,
    primitives: primitives.map((primitive) => ({
      kind: primitive.kind,
      points: primitive.points.map(mapPoint),
    })),
  };
}
