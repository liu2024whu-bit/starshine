const ENDPOINTS = Object.freeze({
  health: "/healthz",
  operators: "/api/v1/operators",
  validate: "/api/v1/workflows/validate",
  plan: "/api/v1/workflows/plan",
  contract: "/api/v1/workflows/contract",
  graph: "/api/v1/workflows/graph",
  explain: "/api/v1/workflows/explain",
});

const state = {
  catalog: null,
  reports: null,
};

const elements = {
  workflow: document.querySelector("#workflow-editor"),
  layerNames: document.querySelector("#layer-names"),
  reviewButton: document.querySelector("#review-button"),
  requestStatus: document.querySelector("#request-status"),
  reviewState: document.querySelector("#review-state"),
  serverVersion: document.querySelector("#server-version"),
  catalogStatus: document.querySelector("#catalog-status"),
  operatorCatalog: document.querySelector("#operator-catalog"),
  overview: document.querySelector("#overview-content"),
  contract: document.querySelector("#contract-content"),
  graph: document.querySelector("#graph-content"),
  explain: document.querySelector("#explain-content"),
  evidence: document.querySelector("#evidence-content"),
};

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

function setRequestStatus(message, isError = false) {
  elements.requestStatus.textContent = message;
  elements.requestStatus.classList.toggle("is-error", isError);
}

function setReviewState(message, isError = false) {
  elements.reviewState.textContent = message;
  elements.reviewState.classList.toggle("badge-error", isError);
  elements.reviewState.classList.toggle("badge-safe", !isError && message === "Reviewed");
}

function apiErrorMessage(payload, status) {
  if (payload && typeof payload === "object") {
    if (payload.diagnostic && typeof payload.diagnostic.message === "string") {
      return payload.diagnostic.message;
    }
    if (typeof payload.message === "string") {
      return payload.message;
    }
  }
  return `Request failed with HTTP ${status}.`;
}

async function requestJson(path, options = {}) {
  const init = {
    method: options.method || "GET",
    headers: {
      accept: "application/json",
    },
    credentials: "same-origin",
  };

  if (options.body !== undefined) {
    init.headers["content-type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }

  const response = await fetch(path, init);
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    throw new Error(`Server returned non-JSON content for ${path}.`);
  }

  if (!response.ok) {
    throw new Error(apiErrorMessage(payload, response.status));
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`Server returned an invalid JSON object for ${path}.`);
  }
  return payload;
}

function parseWorkflow() {
  let value;
  try {
    value = JSON.parse(elements.workflow.value);
  } catch (error) {
    throw new Error(`Workflow JSON is not valid: ${error.message}`);
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Workflow JSON must be an object.");
  }
  return value;
}

function parseLayerNames() {
  return elements.layerNames.value
    .split(/\r?\n/)
    .map((value) => value.trim())
    .filter((value) => value.length > 0);
}

function renderCatalog(catalog) {
  clearNode(elements.operatorCatalog);
  const operators = Array.isArray(catalog.operators) ? catalog.operators : [];
  for (const operator of operators) {
    const name = operator && typeof operator.name === "string" ? operator.name : "unnamed";
    const chip = textElement("span", name, "operator-chip");
    if (operator && typeof operator.summary === "string") {
      chip.title = operator.summary;
    }
    elements.operatorCatalog.appendChild(chip);
  }
  elements.catalogStatus.textContent = `${operators.length} canonical operators`;
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

function renderOverview(reports) {
  clearNode(elements.overview);

  const grid = document.createElement("div");
  grid.className = "summary-grid";
  grid.appendChild(summaryCard("Validation", reports.validation.valid ? "valid" : "invalid"));
  grid.appendChild(summaryCard("Workflow steps", reports.plan.step_count));
  grid.appendChild(
    summaryCard("Required external layers", formatList(reports.plan.required_external_layers)),
  );
  grid.appendChild(summaryCard("Terminal layers", formatList(reports.plan.terminal_layers)));
  elements.overview.appendChild(grid);

  const digests = document.createElement("div");
  digests.className = "digest-list";
  digests.appendChild(digestRow("Workflow", reports.plan.workflow_digest));
  digests.appendChild(digestRow("Plan", reports.plan.plan_digest));
  digests.appendChild(digestRow("Contract", reports.contract.contract_digest));
  digests.appendChild(digestRow("Graph", reports.graph.graph_digest));
  digests.appendChild(digestRow("Explanation", reports.explain.explanation_digest));
  elements.overview.appendChild(digests);
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

function renderContract(contract) {
  clearNode(elements.contract);
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
  elements.contract.appendChild(stack);
}

function renderGraph(graph) {
  clearNode(elements.graph);

  const nodesHeading = textElement("h3", "Nodes");
  elements.graph.appendChild(nodesHeading);
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
  elements.graph.appendChild(nodes);

  elements.graph.appendChild(textElement("h3", "Edges"));
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
  elements.graph.appendChild(edges);
}

function renderExplanation(explanation) {
  clearNode(elements.explain);
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
  elements.explain.appendChild(stack);
}

function renderEvidence(reports) {
  clearNode(elements.evidence);
  const pre = document.createElement("pre");
  pre.className = "raw-block";
  pre.textContent = JSON.stringify(reports, null, 2);
  elements.evidence.appendChild(pre);
}

function renderReports(reports) {
  renderOverview(reports);
  renderContract(reports.contract);
  renderGraph(reports.graph);
  renderExplanation(reports.explain);
  renderEvidence(reports);
}

async function loadServiceMetadata() {
  try {
    const [health, catalog] = await Promise.all([
      requestJson(ENDPOINTS.health),
      requestJson(ENDPOINTS.operators),
    ]);
    state.catalog = catalog;
    renderCatalog(catalog);
    const version = health.core_version || "unknown";
    elements.serverVersion.textContent = `Core ${version}`;
  } catch (error) {
    elements.catalogStatus.textContent = "Catalog unavailable";
    setRequestStatus(error.message, true);
    setReviewState("Server unavailable", true);
  }
}

async function reviewWorkflow() {
  elements.reviewButton.disabled = true;
  setRequestStatus("Validating workflow…");
  setReviewState("Reviewing");

  try {
    const workflow = parseWorkflow();
    const layerNames = parseLayerNames();
    const request = {
      workflow,
      layer_names: layerNames,
    };

    const validation = await requestJson(ENDPOINTS.validate, {
      method: "POST",
      body: request,
    });

    setRequestStatus("Building canonical review reports…");
    const [plan, contract, graph, explain] = await Promise.all([
      requestJson(ENDPOINTS.plan, { method: "POST", body: request }),
      requestJson(ENDPOINTS.contract, { method: "POST", body: request }),
      requestJson(ENDPOINTS.graph, { method: "POST", body: request }),
      requestJson(ENDPOINTS.explain, { method: "POST", body: request }),
    ]);

    const planDigest = plan.plan_digest;
    if (
      contract.plan_digest !== planDigest ||
      graph.plan_digest !== planDigest ||
      explain.plan_digest !== planDigest ||
      explain.graph_digest !== graph.graph_digest
    ) {
      throw new Error("Server review reports do not share one canonical evidence chain.");
    }

    state.reports = { validation, plan, contract, graph, explain };
    renderReports(state.reports);
    setRequestStatus("Canonical review complete.");
    setReviewState("Reviewed");
  } catch (error) {
    setRequestStatus(error.message, true);
    setReviewState("Review failed", true);
  } finally {
    elements.reviewButton.disabled = false;
  }
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

function initializeTabs() {
  for (const button of document.querySelectorAll(".tab-button")) {
    button.addEventListener("click", () => activatePanel(button));
  }
}

elements.reviewButton.addEventListener("click", reviewWorkflow);
initializeTabs();
loadServiceMetadata();
