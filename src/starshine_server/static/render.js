function clearNode(node) {
  while (node.firstChild) {
    node.removeChild(node.firstChild);
  }
}

function textElement(tag, text, className = "") {
  const element = document.createElement(tag);
  element.textContent = String(text);
  if (className) {
    element.className = className;
  }
  return element;
}

function formatList(values) {
  return Array.isArray(values) && values.length ? values.join(", ") : "none";
}

export function setRequestStatus(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle("is-error", isError);
}

export function setReviewState(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle("badge-error", isError);
  element.classList.toggle("badge-safe", !isError && message === "Reviewed");
}

export function renderCatalog(container, status, catalog) {
  clearNode(container);
  const operators = Array.isArray(catalog.operators) ? catalog.operators : [];
  for (const operator of operators) {
    const name = operator && typeof operator.name === "string" ? operator.name : "unnamed";
    const chip = textElement("span", name, "operator-chip");
    if (operator && typeof operator.summary === "string") {
      chip.title = operator.summary;
    }
    container.appendChild(chip);
  }
  status.textContent = `${operators.length} canonical operators`;
}

function summaryCard(label, value) {
  const card = document.createElement("div");
  card.className = "summary-card";
  card.appendChild(textElement("div", label, "label"));
  card.appendChild(textElement("div", value, "value"));
  return card;
}

function digestRow(label, value) {
  const row = document.createElement("div");
  row.className = "digest-row";
  row.appendChild(textElement("strong", label));
  row.appendChild(textElement("code", value || "not reported"));
  return row;
}

function renderOverview(container, reports) {
  clearNode(container);

  const grid = document.createElement("div");
  grid.className = "summary-grid";
  grid.appendChild(summaryCard("Validation", reports.validation.valid ? "valid" : "invalid"));
  grid.appendChild(summaryCard("Workflow steps", reports.plan.step_count));
  grid.appendChild(
    summaryCard("Required external layers", formatList(reports.plan.required_external_layers)),
  );
  grid.appendChild(summaryCard("Terminal layers", formatList(reports.plan.terminal_layers)));
  container.appendChild(grid);

  const digests = document.createElement("div");
  digests.className = "digest-list";
  digests.appendChild(digestRow("Workflow", reports.plan.workflow_digest));
  digests.appendChild(digestRow("Plan", reports.plan.plan_digest));
  digests.appendChild(digestRow("Contract", reports.contract.contract_digest));
  digests.appendChild(digestRow("Graph", reports.graph.graph_digest));
  digests.appendChild(digestRow("Explanation", reports.explain.explanation_digest));
  container.appendChild(digests);
}

function appendList(card, label, values) {
  card.appendChild(textElement("p", label));
  const list = document.createElement("ul");
  list.className = "report-list";
  if (!Array.isArray(values) || values.length === 0) {
    list.appendChild(textElement("li", "none"));
  } else {
    for (const value of values) {
      list.appendChild(textElement("li", value));
    }
  }
  card.appendChild(list);
}

function renderContract(container, contract) {
  clearNode(container);
  const stack = document.createElement("div");
  stack.className = "report-stack";

  const layers = Array.isArray(contract.layers) ? contract.layers : [];
  for (const layer of layers) {
    const card = document.createElement("article");
    card.className = "report-card";
    card.appendChild(textElement("h3", layer.name || "Unnamed layer"));
    card.appendChild(
      textElement(
        "p",
        layer.unused
          ? "Declared but unused by this workflow."
          : `Used by ${layer.use_count ?? 0} workflow input(s).`,
      ),
    );

    const uses = Array.isArray(layer.uses) ? layer.uses : [];
    for (const use of uses) {
      const geometry = formatList(use.geometry_types);
      const crsMode = use.crs && typeof use.crs.mode === "string" ? use.crs.mode : "not reported";
      card.appendChild(
        textElement(
          "p",
          `Step ${use.step_index}: ${use.operation} / ${use.input_name} · geometry: ${geometry} · CRS: ${crsMode}`,
        ),
      );
      const requiredFields = Array.isArray(use.required_fields)
        ? use.required_fields.map((field) => field.name)
        : [];
      appendList(card, "Required fields", requiredFields);
    }
    stack.appendChild(card);
  }

  if (layers.length === 0) {
    stack.appendChild(textElement("p", "No external layer contracts were reported.", "muted"));
  }
  container.appendChild(stack);
}

function renderGraph(container, graph) {
  clearNode(container);

  container.appendChild(textElement("h3", "Nodes"));
  const nodes = document.createElement("div");
  nodes.className = "node-grid";

  for (const node of Array.isArray(graph.nodes) ? graph.nodes : []) {
    const card = document.createElement("article");
    card.className = "report-card";
    card.appendChild(textElement("div", node.kind || "node", "node-kind"));
    card.appendChild(textElement("h3", node.label || node.id || "Unnamed node"));
    card.appendChild(textElement("p", node.id || "No node id"));
    nodes.appendChild(card);
  }
  container.appendChild(nodes);

  container.appendChild(textElement("h3", "Edges"));
  const edges = document.createElement("div");
  edges.className = "edge-list";
  for (const edge of Array.isArray(graph.edges) ? graph.edges : []) {
    const item = document.createElement("div");
    item.className = "edge-item";
    item.appendChild(textElement("span", edge.source || "?"));
    item.appendChild(textElement("span", `→ ${edge.label || edge.kind || ""}`, "edge-arrow"));
    item.appendChild(textElement("span", edge.target || "?"));
    edges.appendChild(item);
  }
  container.appendChild(edges);
}

function renderExplanation(container, explanation) {
  clearNode(container);
  const stack = document.createElement("div");
  stack.className = "report-stack";

  for (const step of Array.isArray(explanation.steps) ? explanation.steps : []) {
    const card = document.createElement("article");
    card.className = "report-card";
    card.appendChild(textElement("div", `Step ${step.index}`, "node-kind"));
    card.appendChild(textElement("h3", step.operation || "Unnamed operation"));
    card.appendChild(textElement("p", step.summary || "No summary reported."));
    card.appendChild(textElement("p", `Output: ${step.output || "not reported"}`));
    card.appendChild(
      textElement("p", `Direct dependencies: ${formatList(step.dependencies)}`),
    );

    const parameterLines = Array.isArray(step.parameters)
      ? step.parameters.map(
          (item) => `${item.name} = ${JSON.stringify(item.value)} (${item.source})`,
        )
      : [];
    appendList(card, "Resolved parameters", parameterLines);
    stack.appendChild(card);
  }
  container.appendChild(stack);
}

function renderEvidence(container, reports) {
  clearNode(container);
  const pre = document.createElement("pre");
  pre.className = "raw-block";
  pre.textContent = JSON.stringify(reports, null, 2);
  container.appendChild(pre);
}

export function renderReports(containers, reports) {
  renderOverview(containers.overview, reports);
  renderContract(containers.contract, reports.contract);
  renderGraph(containers.graph, reports.graph);
  renderExplanation(containers.explain, reports.explain);
  renderEvidence(containers.evidence, reports);
}

function activatePanel(button) {
  const targetId = button.dataset.panelTarget;
  for (const candidate of document.querySelectorAll(".tab-button")) {
    const active = candidate === button;
    candidate.classList.toggle("is-active", active);
    candidate.setAttribute("aria-selected", active ? "true" : "false");
  }
  for (const panel of document.querySelectorAll(".tab-panel")) {
    panel.hidden = panel.id !== targetId;
  }
}

export function initializeTabs() {
  for (const button of document.querySelectorAll(".tab-button")) {
    button.addEventListener("click", () => activatePanel(button));
  }
}


function helperText(text) {
  return textElement("p", text, "field-help");
}

function metaChip(text) {
  return textElement("span", text, "meta-chip");
}

export function populateOperatorSelect(select, catalog) {
  clearNode(select);
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Choose a canonical operator";
  select.appendChild(placeholder);

  const operators = catalog && Array.isArray(catalog.operators) ? catalog.operators : [];
  for (const operator of operators) {
    if (!operator || typeof operator.name !== "string") {
      continue;
    }
    const option = document.createElement("option");
    option.value = operator.name;
    option.textContent = operator.name;
    select.appendChild(option);
  }

  select.disabled = operators.length === 0;
}

function appendInputContractHints(container, input) {
  const contract = input && input.contract && typeof input.contract === "object"
    ? input.contract
    : null;
  if (!contract) {
    return;
  }

  const row = document.createElement("div");
  row.className = "field-meta";

  const geometryTypes = Array.isArray(contract.geometry_types) ? contract.geometry_types : [];
  row.appendChild(
    metaChip(geometryTypes.length ? `geometry: ${geometryTypes.join(" / ")}` : "geometry: any validated type"),
  );

  if (contract.crs && typeof contract.crs.mode === "string") {
    row.appendChild(metaChip(`CRS: ${contract.crs.mode}`));
    if (typeof contract.crs.equivalent_to_input === "string") {
      row.appendChild(metaChip(`CRS = ${contract.crs.equivalent_to_input}`));
    }
  }

  container.appendChild(row);

  for (const note of Array.isArray(contract.notes) ? contract.notes : []) {
    container.appendChild(helperText(note));
  }
}

function parameterDefaultText(parameter) {
  if (!parameter || !Object.hasOwn(parameter, "default")) {
    return null;
  }
  return JSON.stringify(parameter.default);
}

export function renderStepBuilder(container, operator, layerNames) {
  clearNode(container);

  if (!operator) {
    container.appendChild(
      textElement("p", "Choose an operator to see its canonical inputs and parameters.", "builder-empty"),
    );
    return;
  }

  const intro = document.createElement("div");
  intro.className = "builder-operator-summary";
  intro.appendChild(textElement("strong", operator.name));
  intro.appendChild(helperText(operator.summary || "No summary reported by the catalog."));
  intro.appendChild(helperText(`Output CRS behavior: ${operator.output_crs || "not reported"}`));
  container.appendChild(intro);

  const listId = "builder-layer-suggestions";
  const datalist = document.createElement("datalist");
  datalist.id = listId;
  for (const layerName of Array.isArray(layerNames) ? layerNames : []) {
    const option = document.createElement("option");
    option.value = layerName;
    datalist.appendChild(option);
  }
  container.appendChild(datalist);

  const inputs = Array.isArray(operator.inputs) ? operator.inputs : [];
  for (const [index, input] of inputs.entries()) {
    const field = document.createElement("div");
    field.className = "builder-field";
    const fieldId = `builder-input-${index}`;

    const label = document.createElement("label");
    label.htmlFor = fieldId;
    label.textContent = `Input · ${input.name}`;
    field.appendChild(label);

    const control = document.createElement("input");
    control.id = fieldId;
    control.className = "builder-control";
    control.type = "text";
    control.setAttribute("list", listId);
    control.dataset.stepInput = input.name;
    control.autocomplete = "off";
    field.appendChild(control);

    field.appendChild(helperText(input.description || "No input description reported."));
    appendInputContractHints(field, input);
    container.appendChild(field);
  }

  const parameters = Array.isArray(operator.parameters) ? operator.parameters : [];
  for (const [index, parameter] of parameters.entries()) {
    const field = document.createElement("div");
    field.className = "builder-field";
    const fieldId = `builder-parameter-${index}`;

    const labelRow = document.createElement("div");
    labelRow.className = "builder-label-row";
    const label = document.createElement("label");
    label.htmlFor = fieldId;
    label.textContent = `Parameter · ${parameter.name}`;
    labelRow.appendChild(label);

    const defaultText = parameterDefaultText(parameter);
    if (parameter.required) {
      labelRow.appendChild(metaChip("required"));
    } else if (defaultText !== null) {
      labelRow.appendChild(metaChip(`Core default: ${defaultText}`));
    } else {
      labelRow.appendChild(metaChip("optional"));
    }
    field.appendChild(labelRow);

    const control = document.createElement("input");
    control.id = fieldId;
    control.className = "builder-control";
    control.type = "text";
    control.dataset.stepParameter = parameter.name;
    control.autocomplete = "off";
    control.placeholder = parameter.required
      ? "Enter a draft value; Server validates it"
      : "Leave blank to let Core resolve the default/optional value";
    field.appendChild(control);

    field.appendChild(helperText(parameter.description || "No parameter description reported."));
    const schema = parameter.schema && typeof parameter.schema === "object"
      ? JSON.stringify(parameter.schema)
      : "{}";
    field.appendChild(textElement("code", `Schema: ${schema}`, "schema-hint"));
    container.appendChild(field);
  }

  const outputField = document.createElement("div");
  outputField.className = "builder-field";
  const outputLabel = document.createElement("label");
  outputLabel.htmlFor = "builder-output";
  outputLabel.textContent = "Output layer name";
  outputField.appendChild(outputLabel);

  const output = document.createElement("input");
  output.id = "builder-output";
  output.className = "builder-control";
  output.type = "text";
  output.dataset.stepOutput = "true";
  output.autocomplete = "off";
  output.placeholder = "e.g. analysis_result";
  outputField.appendChild(output);
  outputField.appendChild(
    helperText("The browser does not check collisions or naming rules; Server validation remains authoritative."),
  );
  container.appendChild(outputField);
}


export function updateLayerSuggestions(container, layerNames) {
  const datalist = container.querySelector("#builder-layer-suggestions");
  if (!datalist) {
    return;
  }
  clearNode(datalist);
  for (const layerName of Array.isArray(layerNames) ? layerNames : []) {
    const option = document.createElement("option");
    option.value = layerName;
    datalist.appendChild(option);
  }
}

export function resetReview(containers, message = "Workflow changes have not been reviewed yet.") {
  const targets = [
    containers.overview,
    containers.contract,
    containers.graph,
    containers.explain,
    containers.evidence,
  ];
  for (const target of targets) {
    clearNode(target);
    const placeholder = document.createElement("div");
    placeholder.className = "empty-state";
    placeholder.appendChild(textElement("p", message));
    target.appendChild(placeholder);
  }
}


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

export function resetPreflightWorkspace(inputs, result, message) {
  clearNode(inputs);
  inputs.appendChild(preflightPlaceholder(message));
  clearNode(result);
  result.appendChild(preflightPlaceholder("No current Preflight evidence."));
}
