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

export function renderPreflight(container, report) {
  clearNode(container);

  if (!report) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.appendChild(
      textElement("p", "Run canonical Preflight after a fresh review to inspect loaded layer assurance."),
    );
    container.appendChild(empty);
    return;
  }

  const summary = document.createElement("div");
  summary.className = "summary-grid";
  summary.appendChild(summaryCard("Status", report.valid ? "passed" : "failed"));
  summary.appendChild(summaryCard("Checked layers", report.checked_layer_count ?? 0));
  summary.appendChild(summaryCard("Errors", report.error_count ?? 0));
  summary.appendChild(summaryCard("Warnings", report.warning_count ?? 0));
  container.appendChild(summary);

  const layerStack = document.createElement("div");
  layerStack.className = "report-stack";
  layerStack.appendChild(textElement("h3", "Layer assurance"));
  for (const layer of Array.isArray(report.layers) ? report.layers : []) {
    const card = document.createElement("article");
    card.className = "report-card";
    card.appendChild(textElement("div", layer.status || "unknown", "node-kind"));
    card.appendChild(textElement("h3", layer.name || "Unnamed layer"));
    card.appendChild(
      textElement(
        "p",
        `Features: ${layer.feature_count ?? "not checked"} · CRS: ${layer.declared_crs ?? "not declared"} · errors: ${layer.error_count ?? 0} · warnings: ${layer.warning_count ?? 0}`,
      ),
    );
    const geometry = layer.geometry_counts && typeof layer.geometry_counts === "object"
      ? Object.entries(layer.geometry_counts).map(([name, count]) => `${name}: ${count}`)
      : [];
    appendList(card, "Geometry counts", geometry);
    layerStack.appendChild(card);
  }
  container.appendChild(layerStack);

  const findingStack = document.createElement("div");
  findingStack.className = "report-stack";
  findingStack.appendChild(textElement("h3", "Findings"));
  const findings = Array.isArray(report.findings) ? report.findings : [];
  if (!findings.length) {
    findingStack.appendChild(textElement("p", "No Preflight findings were reported.", "muted"));
  }
  for (const finding of findings) {
    const card = document.createElement("article");
    card.className = "report-card";
    card.appendChild(textElement("div", finding.severity || "finding", "node-kind"));
    card.appendChild(textElement("h3", finding.code || "Finding"));
    card.appendChild(textElement("p", finding.message || "No message reported."));
    card.appendChild(
      textElement(
        "p",
        `Layer: ${finding.layer || "not reported"} · occurrences: ${finding.occurrence_count ?? 1}`,
      ),
    );
    if (Array.isArray(finding.feature_indexes) && finding.feature_indexes.length) {
      appendList(card, "Sample feature indexes", finding.feature_indexes);
    }
    findingStack.appendChild(card);
  }
  container.appendChild(findingStack);

  const remaining = document.createElement("article");
  remaining.className = "report-card";
  remaining.appendChild(textElement("h3", "Remaining execution-time checks"));
  appendList(remaining, "Not proven by Preflight", report.remaining_checks || []);
  container.appendChild(remaining);

  const digests = document.createElement("div");
  digests.className = "digest-list";
  digests.appendChild(digestRow("Workflow", report.workflow_digest));
  digests.appendChild(digestRow("Plan", report.plan_digest));
  digests.appendChild(digestRow("Contract", report.contract_digest));
  digests.appendChild(digestRow("Preflight", report.preflight_digest));
  container.appendChild(digests);
}

export function renderEvidence(container, reports) {
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
