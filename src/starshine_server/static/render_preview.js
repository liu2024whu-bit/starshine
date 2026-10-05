import {
  clearNode,
  helperText,
  metaChip,
  textElement,
} from "./dom.js";

const SVG_NS = "http://www.w3.org/2000/svg";

function placeholder(message) {
  const element = document.createElement("div");
  element.className = "empty-state";
  element.appendChild(textElement("p", message));
  return element;
}

export function resetResultPreview(
  container,
  message = "Execute a current passing evidence chain to preview its result.",
) {
  clearNode(container);
  container.appendChild(placeholder(message));
}

function coordinateText(value) {
  return Number.isFinite(value) ? String(Number(value.toPrecision(8))) : "not reported";
}

function svgElement(name) {
  return document.createElementNS(SVG_NS, name);
}

export function renderResultPreview(container, preview) {
  clearNode(container);

  const notice = document.createElement("aside");
  notice.className = "boundary-note";
  notice.appendChild(textElement("strong", "Coordinate-space preview only — not projection-aware."));
  notice.appendChild(
    textElement(
      "span",
      "The browser fits returned finite 2D coordinates directly into this SVG. It does not parse CRS, reproject, validate, repair, or spatially analyze the canonical result.",
    ),
  );
  container.appendChild(notice);

  if (!preview || !Array.isArray(preview.primitives) || preview.primitives.length === 0) {
    container.appendChild(
      placeholder("The canonical result contains no finite 2D coordinate fragments this preview can draw."),
    );
    return;
  }

  const meta = document.createElement("div");
  meta.className = "field-meta";
  meta.appendChild(metaChip(`display primitives: ${preview.primitive_count}`));
  meta.appendChild(metaChip(`2D coordinates: ${preview.coordinate_count}`));
  container.appendChild(meta);

  if (preview.bounds) {
    container.appendChild(
      helperText(
        `Raw coordinate extent: [${coordinateText(preview.bounds.min_x)}, ${coordinateText(preview.bounds.min_y)}] → [${coordinateText(preview.bounds.max_x)}, ${coordinateText(preview.bounds.max_y)}]`,
      ),
    );
  }

  const frame = document.createElement("div");
  frame.className = "result-preview-frame";

  const svg = svgElement("svg");
  svg.classList.add("result-preview-svg");
  svg.setAttribute("viewBox", `0 0 ${preview.width} ${preview.height}`);
  svg.setAttribute("role", "img");
  svg.setAttribute(
    "aria-label",
    "Projection-free coordinate-space preview of the current canonical result",
  );

  for (const primitive of preview.primitives) {
    if (primitive.kind === "point") {
      const [point] = primitive.points;
      if (!point) {
        continue;
      }
      const circle = svgElement("circle");
      circle.setAttribute("cx", String(point[0]));
      circle.setAttribute("cy", String(point[1]));
      circle.setAttribute("r", "4");
      circle.classList.add("preview-point");
      svg.appendChild(circle);
      continue;
    }

    const points = primitive.points
      .map(([x, y]) => `${x},${y}`)
      .join(" ");
    if (!points) {
      continue;
    }

    const shape = svgElement(primitive.kind === "ring" ? "polygon" : "polyline");
    shape.setAttribute("points", points);
    shape.classList.add(primitive.kind === "ring" ? "preview-ring" : "preview-line");
    svg.appendChild(shape);
  }

  frame.appendChild(svg);
  container.appendChild(frame);
  container.appendChild(
    helperText(
      "Raw result JSON and the Core manifest in the Execute tab remain authoritative if this visual preview is incomplete or distorted.",
    ),
  );
}
