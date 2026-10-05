import {
  clearNode,
  digestRow,
  helperText,
  metaChip,
  summaryCard,
  textElement,
} from "./dom.js";

function placeholder(message) {
  const element = document.createElement("div");
  element.className = "empty-state";
  element.appendChild(textElement("p", message));
  return element;
}

export function renderExecutionControls(outputSelect, executeButton, outputNames, enabled) {
  clearNode(outputSelect);

  const names = Array.isArray(outputNames) ? outputNames : [];
  if (names.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No canonical terminal outputs";
    outputSelect.appendChild(option);
    outputSelect.disabled = true;
    executeButton.disabled = true;
    return;
  }

  for (const name of names) {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    outputSelect.appendChild(option);
  }

  outputSelect.disabled = !enabled;
  executeButton.disabled = !enabled;
}

export function resetExecutionResult(
  container,
  message = "No current execution evidence.",
) {
  clearNode(container);
  container.appendChild(placeholder(message));
}

function renderManifestSummary(container, manifest) {
  const summary = document.createElement("div");
  summary.className = "summary-grid";
  summary.appendChild(summaryCard("Manifest version", manifest.manifest_version ?? "not reported"));
  summary.appendChild(summaryCard("Starshine version", manifest.starshine_version ?? "not reported"));
  summary.appendChild(summaryCard("Workflow version", manifest.workflow_version ?? "not reported"));
  summary.appendChild(
    summaryCard(
      "Output layer",
      manifest.output_layer && manifest.output_layer.name
        ? manifest.output_layer.name
        : "not reported",
    ),
  );
  container.appendChild(summary);

  const evidence = document.createElement("div");
  evidence.className = "digest-list";
  evidence.appendChild(digestRow("Workflow", manifest.workflow_digest));
  evidence.appendChild(
    digestRow(
      "Output result",
      manifest.output_layer && manifest.output_layer.digest
        ? manifest.output_layer.digest
        : "not reported",
    ),
  );
  container.appendChild(evidence);

  const outputMeta = document.createElement("div");
  outputMeta.className = "field-meta";
  const outputCrs = manifest.output_layer ? manifest.output_layer.crs : null;
  outputMeta.appendChild(metaChip(`output CRS: ${outputCrs || "not declared"}`));
  outputMeta.appendChild(
    metaChip(
      `executed steps: ${Array.isArray(manifest.executed_steps) ? manifest.executed_steps.length : "not reported"}`,
    ),
  );
  container.appendChild(outputMeta);

  const inputs = manifest.input_layers && typeof manifest.input_layers === "object"
    ? Object.entries(manifest.input_layers)
    : [];
  if (inputs.length) {
    container.appendChild(textElement("h3", "Input-layer manifest evidence"));
    const stack = document.createElement("div");
    stack.className = "report-stack";
    for (const [name, layer] of inputs) {
      const card = document.createElement("article");
      card.className = "report-card";
      card.appendChild(textElement("h3", name));
      card.appendChild(textElement("p", `CRS: ${layer.crs || "not declared"}`));
      card.appendChild(textElement("code", layer.digest || "not reported"));
      stack.appendChild(card);
    }
    container.appendChild(stack);
  }
}

function rawEvidence(title, value) {
  const card = document.createElement("article");
  card.className = "report-card";
  card.appendChild(textElement("h3", title));
  const pre = document.createElement("pre");
  pre.className = "raw-block";
  pre.textContent = JSON.stringify(value, null, 2);
  card.appendChild(pre);
  return card;
}

export function renderExecutionResult(container, execution) {
  clearNode(container);

  const notice = document.createElement("aside");
  notice.className = "boundary-note";
  notice.appendChild(
    textElement(
      "strong",
      "Result and provenance below are canonical Server/Core execution evidence.",
    ),
  );
  notice.appendChild(
    textElement(
      "span",
      "The browser does not recompute geometry, CRS, result digests, or manifest values.",
    ),
  );
  container.appendChild(notice);

  const status = document.createElement("div");
  status.className = "field-meta";
  status.appendChild(metaChip(`status: ${execution.status || "not reported"}`));
  status.appendChild(metaChip(`output: ${execution.output_layer || "not reported"}`));
  if (execution.execution_policy && execution.execution_policy.mode) {
    status.appendChild(metaChip(`mode: ${execution.execution_policy.mode}`));
  }
  container.appendChild(status);

  container.appendChild(textElement("h3", "Canonical reproducibility manifest"));
  renderManifestSummary(container, execution.manifest || {});

  container.appendChild(textElement("h3", "Raw execution evidence"));
  const raw = document.createElement("div");
  raw.className = "report-stack";
  raw.appendChild(rawEvidence("Result GeoJSON", execution.result));
  raw.appendChild(rawEvidence("Manifest JSON", execution.manifest));
  raw.appendChild(rawEvidence("Execution Preflight", execution.preflight));
  container.appendChild(raw);

  container.appendChild(
    helperText(
      "A visual map is intentionally deferred; this view preserves the canonical result and provenance before adding presentation-specific geometry rendering.",
    ),
  );
}
