import {
  appendList,
  clearNode,
  digestRow,
  helperText,
  metaChip,
  summaryCard,
  textElement,
} from "./dom.js";

function preflightPlaceholder(message) {
  const placeholder = document.createElement("div");
  placeholder.className = "empty-state";
  placeholder.appendChild(textElement("p", message));
  return placeholder;
}

function contractLayer(contract, name) {
  const layers = contract && Array.isArray(contract.layers) ? contract.layers : [];
  return layers.find((layer) => layer && layer.name === name) || null;
}

function formatByteLimit(value) {
  if (!Number.isFinite(value)) {
    return "not reported";
  }
  if (value >= 1024 * 1024 && value % (1024 * 1024) === 0) {
    return `${value / (1024 * 1024)} MiB`;
  }
  if (value >= 1024 && value % 1024 === 0) {
    return `${value / 1024} KiB`;
  }
  return `${value} bytes`;
}

export function renderPreflightBindings(container, requiredNames, contract, drafts, limits) {
  clearNode(container);

  const names = Array.isArray(requiredNames) ? requiredNames : [];
  if (names.length === 0) {
    container.appendChild(
      preflightPlaceholder("The current canonical plan has no required external layers to Preflight."),
    );
    return;
  }

  const intro = document.createElement("div");
  intro.className = "preflight-limit-card";
  intro.appendChild(textElement("strong", "Server-enforced inline boundary"));
  const limitParts = [];
  if (limits && typeof limits === "object") {
    limitParts.push(`request ≤ ${formatByteLimit(limits.max_request_bytes)}`);
    if (Number.isFinite(limits.max_layers)) {
      limitParts.push(`layers ≤ ${limits.max_layers}`);
    }
    if (Number.isFinite(limits.max_features_per_layer)) {
      limitParts.push(`features/layer ≤ ${limits.max_features_per_layer}`);
    }
    if (Number.isFinite(limits.max_total_features)) {
      limitParts.push(`total features ≤ ${limits.max_total_features}`);
    }
  }
  intro.appendChild(
    helperText(
      limitParts.length
        ? limitParts.join(" · ")
        : "Current Preflight limits were not reported by the Server.",
    ),
  );
  intro.appendChild(
    helperText("These limits are informational here; Server enforcement remains authoritative."),
  );
  container.appendChild(intro);

  const stack = document.createElement("div");
  stack.className = "preflight-binding-stack";

  for (const [index, name] of names.entries()) {
    const card = document.createElement("article");
    card.className = "preflight-binding";
    card.appendChild(textElement("h3", name));

    const layerContract = contractLayer(contract, name);
    if (layerContract) {
      card.appendChild(
        helperText(
          layerContract.use_count
            ? `Canonical contract uses this layer ${layerContract.use_count} time(s).`
            : "Canonical contract reports no active uses for this layer.",
        ),
      );

      for (const use of Array.isArray(layerContract.uses) ? layerContract.uses : []) {
        const row = document.createElement("div");
        row.className = "field-meta";
        const geometryTypes = Array.isArray(use.geometry_types) ? use.geometry_types : [];
        row.appendChild(
          metaChip(
            geometryTypes.length
              ? `geometry: ${geometryTypes.join(" / ")}`
              : "geometry: any validated type",
          ),
        );
        if (use.crs && typeof use.crs.mode === "string") {
          row.appendChild(metaChip(`CRS: ${use.crs.mode}`));
        }
        const requiredFields = Array.isArray(use.required_fields)
          ? use.required_fields.map((field) => field.name).filter(Boolean)
          : [];
        if (requiredFields.length) {
          row.appendChild(metaChip(`fields: ${requiredFields.join(", ")}`));
        }
        card.appendChild(row);
      }
    }

    const label = document.createElement("label");
    const fieldId = `preflight-layer-${index}`;
    label.htmlFor = fieldId;
    label.textContent = "Inline GeoJSON";
    card.appendChild(label);

    const textarea = document.createElement("textarea");
    textarea.id = fieldId;
    textarea.className = "preflight-layer-editor";
    textarea.spellcheck = false;
    textarea.dataset.preflightLayer = name;
    textarea.value = drafts && typeof drafts[name] === "string" ? drafts[name] : "";
    textarea.placeholder = '{"type":"FeatureCollection","features":[]}';
    card.appendChild(textarea);
    card.appendChild(
      helperText(
        "Paste JSON only. Structure, geometry, CRS, fields, and counts are checked by Server/Core Preflight.",
      ),
    );
    stack.appendChild(card);
  }

  container.appendChild(stack);
}

function geometrySummary(counts) {
  if (!counts || typeof counts !== "object") {
    return "none reported";
  }
  const entries = Object.entries(counts);
  if (entries.length === 0) {
    return "none reported";
  }
  return entries.map(([name, count]) => `${name} × ${count}`).join(", ");
}

export function renderPreflightReport(container, report) {
  clearNode(container);

  const summary = document.createElement("div");
  summary.className = "summary-grid";
  summary.appendChild(summaryCard("Status", report.valid ? "PASS" : "FAIL"));
  summary.appendChild(
    summaryCard("Checked layers", `${report.checked_layer_count ?? 0} / ${report.layer_count ?? 0}`),
  );
  summary.appendChild(summaryCard("Errors", report.error_count ?? 0));
  summary.appendChild(summaryCard("Warnings", report.warning_count ?? 0));
  container.appendChild(summary);

  const layers = document.createElement("div");
  layers.className = "report-stack preflight-report-stack";
  for (const layer of Array.isArray(report.layers) ? report.layers : []) {
    const card = document.createElement("article");
    card.className = "report-card";
    card.appendChild(textElement("div", layer.status || "unknown", "node-kind"));
    card.appendChild(textElement("h3", layer.name || "Unnamed layer"));
    card.appendChild(
      textElement(
        "p",
        `Features: ${layer.feature_count ?? "not checked"} · CRS: ${layer.declared_crs ?? "not declared"}`,
      ),
    );
    card.appendChild(textElement("p", `Geometry: ${geometrySummary(layer.geometry_counts)}`));
    card.appendChild(
      textElement(
        "p",
        `Errors: ${layer.error_count ?? 0} · Warnings: ${layer.warning_count ?? 0}`,
      ),
    );
    layers.appendChild(card);
  }
  container.appendChild(layers);

  const findings = Array.isArray(report.findings) ? report.findings : [];
  container.appendChild(textElement("h3", "Findings"));
  const findingStack = document.createElement("div");
  findingStack.className = "report-stack";
  if (findings.length === 0) {
    findingStack.appendChild(textElement("p", "No canonical Preflight findings.", "muted"));
  } else {
    for (const finding of findings) {
      const card = document.createElement("article");
      card.className = "report-card";
      card.appendChild(
        textElement(
          "div",
          `${finding.severity || "finding"} · ${finding.code || "unknown"}`,
          "node-kind",
        ),
      );
      card.appendChild(textElement("h3", finding.layer || "Unknown layer"));
      card.appendChild(textElement("p", finding.message || "No finding message reported."));
      card.appendChild(
        textElement("p", `Occurrences: ${finding.occurrence_count ?? "not reported"}`),
      );
      findingStack.appendChild(card);
    }
  }
  container.appendChild(findingStack);

  const remaining = Array.isArray(report.remaining_checks) ? report.remaining_checks : [];
  container.appendChild(textElement("h3", "Remaining execution-time checks"));
  const remainingCard = document.createElement("article");
  remainingCard.className = "report-card";
  appendList(remainingCard, "Core reports these checks remain deferred", remaining);
  container.appendChild(remainingCard);

  const evidence = document.createElement("div");
  evidence.className = "digest-list";
  evidence.appendChild(digestRow("Workflow", report.workflow_digest));
  evidence.appendChild(digestRow("Plan", report.plan_digest));
  evidence.appendChild(digestRow("Contract", report.contract_digest));
  evidence.appendChild(digestRow("Preflight", report.preflight_digest));
  container.appendChild(evidence);
}

export function resetPreflightResult(result, message = "No current Preflight evidence.") {
  clearNode(result);
  result.appendChild(preflightPlaceholder(message));
}

export function resetPreflightWorkspace(inputs, result, message) {
  clearNode(inputs);
  inputs.appendChild(preflightPlaceholder(message));
  resetPreflightResult(result);
}
