import { ENDPOINTS, requestJson } from "./api.js";
import {
  appendDraftStep,
  buildDraftStep,
  findCatalogOperator,
  layerSuggestions,
} from "./editor.js";
import {
  initializeTabs,
  populateOperatorSelect,
  renderCatalog,
  renderReports,
  renderStepBuilder,
  resetReview,
  setRequestStatus,
  setReviewState,
  updateLayerSuggestions,
} from "./render.js";

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
  builderOperator: document.querySelector("#builder-operator"),
  builderFields: document.querySelector("#step-builder-fields"),
  addStepButton: document.querySelector("#add-step-button"),
  builderStatus: document.querySelector("#builder-status"),
  overview: document.querySelector("#overview-content"),
  contract: document.querySelector("#contract-content"),
  graph: document.querySelector("#graph-content"),
  explain: document.querySelector("#explain-content"),
  evidence: document.querySelector("#evidence-content"),
};

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

function currentLayerSuggestions() {
  let workflow = null;
  try {
    workflow = parseWorkflow();
  } catch {
    workflow = null;
  }
  return layerSuggestions(workflow, parseLayerNames());
}

function assertEvidenceChain(plan, contract, graph, explain) {
  const planDigest = plan.plan_digest;
  if (
    contract.plan_digest !== planDigest ||
    graph.plan_digest !== planDigest ||
    explain.plan_digest !== planDigest ||
    explain.graph_digest !== graph.graph_digest
  ) {
    throw new Error("Server review reports do not share one canonical evidence chain.");
  }
}

function selectedOperator() {
  return findCatalogOperator(state.catalog, elements.builderOperator.value);
}

function renderSelectedOperator() {
  const operator = selectedOperator();
  renderStepBuilder(elements.builderFields, operator, currentLayerSuggestions());
  elements.addStepButton.disabled = operator === null;
  setRequestStatus(
    elements.builderStatus,
    operator
      ? "Draft fields come from the canonical catalog; Server validation remains authoritative."
      : "Choose a canonical operator to draft one step.",
  );
}

function collectDraftValues() {
  const inputs = {};
  const parameters = {};

  for (const control of elements.builderFields.querySelectorAll("[data-step-input]")) {
    inputs[control.dataset.stepInput] = control.value;
  }
  for (const control of elements.builderFields.querySelectorAll("[data-step-parameter]")) {
    parameters[control.dataset.stepParameter] = control.value;
  }

  const output = elements.builderFields.querySelector("[data-step-output]");
  return {
    inputs,
    parameters,
    output: output ? output.value : "",
  };
}

function invalidateReview(message = "Workflow changes have not been reviewed yet.") {
  if (state.reports === null) {
    updateLayerSuggestions(elements.builderFields, currentLayerSuggestions());
    return;
  }
  state.reports = null;
  resetReview(elements, message);
  setReviewState(elements.reviewState, "Not reviewed");
  setRequestStatus(elements.requestStatus, message);
  updateLayerSuggestions(elements.builderFields, currentLayerSuggestions());
}

function insertDraftStep() {
  try {
    const workflow = parseWorkflow();
    const operator = selectedOperator();
    if (!operator) {
      throw new Error("Choose a canonical operator before inserting a draft step.");
    }

    const draft = collectDraftValues();
    const step = buildDraftStep(
      operator,
      draft.inputs,
      draft.parameters,
      draft.output,
    );
    const updated = appendDraftStep(workflow, step);
    elements.workflow.value = JSON.stringify(updated, null, 2);

    state.reports = null;
    resetReview(elements, "A draft step was inserted. Run Review workflow for canonical validation.");
    setReviewState(elements.reviewState, "Not reviewed");
    setRequestStatus(
      elements.requestStatus,
      "Draft step inserted; Server/Core have not validated it yet.",
    );
    setRequestStatus(
      elements.builderStatus,
      "Draft inserted into Workflow JSON. Review it before treating the step as valid.",
    );
    renderSelectedOperator();
  } catch (error) {
    setRequestStatus(elements.builderStatus, error.message, true);
  }
}

async function loadServiceMetadata() {
  try {
    const [health, catalog] = await Promise.all([
      requestJson(ENDPOINTS.health),
      requestJson(ENDPOINTS.operators),
    ]);
    state.catalog = catalog;
    renderCatalog(elements.operatorCatalog, elements.catalogStatus, catalog);
    populateOperatorSelect(elements.builderOperator, catalog);
    setRequestStatus(elements.builderStatus, "Choose a canonical operator to draft one step.");
    const version = health.core_version || "unknown";
    elements.serverVersion.textContent = `Core ${version}`;
  } catch (error) {
    elements.catalogStatus.textContent = "Catalog unavailable";
    setRequestStatus(elements.requestStatus, error.message, true);
    setRequestStatus(elements.builderStatus, "Catalog unavailable; assisted editing is disabled.", true);
    setReviewState(elements.reviewState, "Server unavailable", true);
  }
}

async function reviewWorkflow() {
  elements.reviewButton.disabled = true;
  setRequestStatus(elements.requestStatus, "Validating workflow…");
  setReviewState(elements.reviewState, "Reviewing");

  try {
    const request = {
      workflow: parseWorkflow(),
      layer_names: parseLayerNames(),
    };

    const validation = await requestJson(ENDPOINTS.validate, {
      method: "POST",
      body: request,
    });

    setRequestStatus(elements.requestStatus, "Building canonical review reports…");
    const [plan, contract, graph, explain] = await Promise.all([
      requestJson(ENDPOINTS.plan, { method: "POST", body: request }),
      requestJson(ENDPOINTS.contract, { method: "POST", body: request }),
      requestJson(ENDPOINTS.graph, { method: "POST", body: request }),
      requestJson(ENDPOINTS.explain, { method: "POST", body: request }),
    ]);

    assertEvidenceChain(plan, contract, graph, explain);
    state.reports = { validation, plan, contract, graph, explain };
    renderReports(elements, state.reports);
    setRequestStatus(elements.requestStatus, "Canonical review complete.");
    setReviewState(elements.reviewState, "Reviewed");
    updateLayerSuggestions(elements.builderFields, currentLayerSuggestions());
  } catch (error) {
    state.reports = null;
    resetReview(elements, "Review failed; no canonical evidence is current.");
    setRequestStatus(elements.requestStatus, error.message, true);
    setReviewState(elements.reviewState, "Review failed", true);
  } finally {
    elements.reviewButton.disabled = false;
  }
}

elements.reviewButton.addEventListener("click", reviewWorkflow);
elements.builderOperator.addEventListener("change", renderSelectedOperator);
elements.addStepButton.addEventListener("click", insertDraftStep);
elements.workflow.addEventListener("input", () => invalidateReview());
elements.layerNames.addEventListener("input", () => invalidateReview());

initializeTabs();
loadServiceMetadata();
