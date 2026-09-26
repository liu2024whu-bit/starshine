import {
  appendList,
  clearNode,
  digestRow,
  helperText,
  metaChip,
  textElement,
} from "./dom.js";

function jsonText(value) {
  if (value === undefined) {
    return "not reported";
  }
  return JSON.stringify(value);
}

function renderCrsObject(container, crs) {
  const row = document.createElement("div");
  row.className = "field-meta";

  if (!crs || typeof crs !== "object") {
    row.appendChild(metaChip("CRS: not reported"));
    container.appendChild(row);
    return;
  }

  row.appendChild(metaChip(`mode: ${crs.mode || "not reported"}`));
  if (typeof crs.parameter === "string") {
    row.appendChild(metaChip(`parameter: ${crs.parameter}`));
  }
  if (Object.hasOwn(crs, "value")) {
    row.appendChild(metaChip(`value: ${jsonText(crs.value)}`));
  }
  if (typeof crs.equivalent_to_layer === "string") {
    row.appendChild(metaChip(`equivalent to layer: ${crs.equivalent_to_layer}`));
  }
  container.appendChild(row);
}

function renderExternalLayerAssumptions(container, contract) {
  container.appendChild(textElement("h3", "External-layer CRS assumptions"));
  const stack = document.createElement("div");
  stack.className = "report-stack";

  const layers = contract && Array.isArray(contract.layers) ? contract.layers : [];
  for (const layer of layers) {
    const card = document.createElement("article");
    card.className = "report-card";
    card.appendChild(textElement("div", layer.required ? "required" : "declared", "node-kind"));
    card.appendChild(textElement("h3", layer.name || "Unnamed layer"));

    if (layer.unused) {
      card.appendChild(helperText("Canonical contract reports this declared layer as unused."));
    }

    for (const use of Array.isArray(layer.uses) ? layer.uses : []) {
      card.appendChild(
        textElement(
          "p",
          `Step ${use.step_index}: ${use.operation} / input ${use.input_name}`,
        ),
      );
      renderCrsObject(card, use.crs);

      const geometry = Array.isArray(use.geometry_types) && use.geometry_types.length
        ? use.geometry_types
        : ["any validated geometry type"];
      appendList(card, "Canonical geometry preparation", geometry);

      const fields = Array.isArray(use.required_fields)
        ? use.required_fields.map((field) => field.name).filter(Boolean)
        : [];
      appendList(card, "Canonical required fields", fields);
    }

    stack.appendChild(card);
  }

  if (layers.length === 0) {
    stack.appendChild(textElement("p", "No external-layer assumptions were reported.", "muted"));
  }
  container.appendChild(stack);
}

function inputProvenance(input) {
  if (!input || typeof input !== "object") {
    return "not reported";
  }
  if (input.source_kind === "step") {
    return `${input.name} ← ${input.layer} · produced by step ${input.producer_step}`;
  }
  return `${input.name} ← ${input.layer} · ${input.source_kind || "not reported"}`;
}

function parameterProvenance(parameter) {
  if (!parameter || typeof parameter !== "object") {
    return "not reported";
  }
  return `${parameter.name} = ${jsonText(parameter.value)} · ${parameter.source || "not reported"}`;
}

function renderStepAssumptions(container, explanation) {
  container.appendChild(textElement("h3", "Step provenance and output behavior"));
  const stack = document.createElement("div");
  stack.className = "report-stack";

  const steps = explanation && Array.isArray(explanation.steps) ? explanation.steps : [];
  for (const step of steps) {
    const card = document.createElement("article");
    card.className = "report-card";
    card.appendChild(textElement("div", `Step ${step.index}`, "node-kind"));
    card.appendChild(textElement("h3", step.operation || "Unnamed operation"));

    const inputLines = Array.isArray(step.inputs)
      ? step.inputs.map(inputProvenance)
      : [];
    appendList(card, "Canonical input provenance", inputLines);

    const parameterLines = Array.isArray(step.parameters)
      ? step.parameters.map(parameterProvenance)
      : [];
    appendList(card, "Resolved parameter provenance", parameterLines);

    card.appendChild(
      textElement("p", `Output layer: ${step.output || "not reported"}`),
    );
    card.appendChild(
      textElement("p", `Output CRS behavior: ${step.output_crs || "not reported"}`),
    );

    const flags = document.createElement("div");
    flags.className = "field-meta";
    flags.appendChild(metaChip(`deterministic: ${step.deterministic ? "yes" : "no"}`));
    flags.appendChild(metaChip(`terminal output: ${step.terminal ? "yes" : "no"}`));
    card.appendChild(flags);
    stack.appendChild(card);
  }

  container.appendChild(stack);
}

function renderEvidenceChain(container, reports, preflight) {
  container.appendChild(textElement("h3", "Pre-execution evidence chain"));

  const status = document.createElement("div");
  status.className = "field-meta";
  status.appendChild(metaChip("data-free review: current"));
  status.appendChild(metaChip(`Preflight evidence: ${preflight ? "current" : "not available"}`));
  container.appendChild(status);

  const digests = document.createElement("div");
  digests.className = "digest-list";
  digests.appendChild(digestRow("Workflow", reports.plan.workflow_digest));
  digests.appendChild(digestRow("Operator catalog", reports.plan.operator_catalog_digest));
  digests.appendChild(digestRow("Plan", reports.plan.plan_digest));
  digests.appendChild(digestRow("Contract", reports.contract.contract_digest));
  digests.appendChild(digestRow("Graph", reports.graph.graph_digest));
  digests.appendChild(digestRow("Explanation", reports.explain.explanation_digest));
  digests.appendChild(
    digestRow("Preflight", preflight ? preflight.preflight_digest : "not available"),
  );
  container.appendChild(digests);
}

export function resetCrsEvidence(
  container,
  message = "Review the current Workflow to see canonical CRS assumptions and evidence.",
) {
  clearNode(container);
  const placeholder = document.createElement("div");
  placeholder.className = "empty-state";
  placeholder.appendChild(textElement("p", message));
  container.appendChild(placeholder);
}

export function renderCrsEvidence(container, reports, preflight = null) {
  clearNode(container);

  const notice = document.createElement("aside");
  notice.className = "boundary-note";
  notice.appendChild(
    textElement(
      "strong",
      "These are canonical pre-execution assumptions and evidence, not a result manifest.",
    ),
  );
  notice.appendChild(
    textElement(
      "span",
      "Actual supplied-layer CRS is shown after Preflight. Post-execution result provenance requires the Core manifest and is not available in the current browser flow because the Workbench does not execute workflows.",
    ),
  );
  container.appendChild(notice);

  renderExternalLayerAssumptions(container, reports.contract);
  renderStepAssumptions(container, reports.explain);
  renderEvidenceChain(container, reports, preflight);
}
