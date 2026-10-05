import { ENDPOINTS, requestJson } from "./api.js";
import {
  assertPreflightEvidenceChain,
  buildPreflightRequest,
  requiredLayerNames,
} from "./assurance.js";
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
  renderPreflightBindings,
  renderPreflightReport,
  renderReports,
  renderStepBuilder,
  resetPreflightResult,
  resetPreflightWorkspace,
  resetReview,
  setRequestStatus,
  setReviewState,
  updateLayerSuggestions,
} from "./render.js";

const state = {
  catalog: null,
  limits: null,
  reports: null,
  preflight: null,
  layerDrafts: {},
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
  preflightInputs: document.querySelector("#preflight-inputs"),
  preflightButton: document.querySelector("#preflight-button"),
  preflightStatus: document.querySelector("#preflight-status"),
  preflightResult: document.querySelector("#preflight-result"),
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

function assertReviewEvidenceChain(plan, contract, graph, explain) {
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

function disablePreflightUntilReview(message) {
  state.preflight = null;
  elements.preflightButton.disabled = true;
  resetPreflightWorkspace(elements.preflightInputs, elements.preflightResult, message);
  setRequestStatus(elements.preflightStatus, message);
}

function preparePreflightForCurrentReview() {
  const names = requiredLayerNames(state.reports);
  state.preflight = null;
  renderPreflightBindings(
    elements.preflightInputs,
    names,
    state.reports.contract,
    state.layerDrafts,
    state.limits && state.limits.inline_preflight,
  );
  resetPreflightResult(elements.preflightResult);
  elements.preflightButton.disabled = names.length === 0;
  setRequestStatus(
    elements.preflightStatus,
    names.length
      ? "Paste JSON for one or more required layers, then run canonical Preflight."
      : "The current canonical plan has no required external layers to Preflight.",
  );
}

function invalidateReview(message = "Workflow changes have not been reviewed yet.") {
  state.reports = null;
  resetReview(elements, message);
  setReviewState(elements.reviewState, "Not reviewed");
  setRequestStatus(elements.requestStatus, message);
  disablePreflightUntilReview("Review the current Workflow before running Preflight.");
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

    invalidateReview("A draft step was inserted. Run Review workflow for canonical validation.");
    renderSelectedOperator();
    setRequestStatus(
      elements.builderStatus,
      "Draft inserted into Workflow JSON. Review it before treating the step as valid.",
    );
  } catch (error) {
    setRequestStatus(elements.builderStatus, error.message, true);
  }
}

async function loadServiceMetadata() {
  try {
    const [health, catalog, limits] = await Promise.all([
      requestJson(ENDPOINTS.health),
      requestJson(ENDPOINTS.operators),
      requestJson(ENDPOINTS.limits),
    ]);
    state.catalog = catalog;
    state.limits = limits;
    renderCatalog(elements.operatorCatalog, elements.catalogStatus, catalog);
    populateOperatorSelect(elements.builderOperator, catalog);
    setRequestStatus(elements.builderStatus, "Choose a canonical operator to draft one step.");
    const version = health.core_version || "unknown";
    elements.serverVersion.textContent = `Core ${version}`;
  } catch (error) {
    elements.catalogStatus.textContent = "Catalog unavailable";
    setRequestStatus(elements.requestStatus, error.message, true);
    setRequestStatus(elements.builderStatus, "Catalog unavailable; assisted editing is disabled.", true);
    setRequestStatus(elements.preflightStatus, "Server metadata is unavailable.", true);
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

    assertReviewEvidenceChain(plan, contract, graph, explain);
    state.reports = { validation, plan, contract, graph, explain };
    renderReports(elements, state.reports);
    preparePreflightForCurrentReview();
    setRequestStatus(elements.requestStatus, "Canonical review complete.");
    setReviewState(elements.reviewState, "Reviewed");
    updateLayerSuggestions(elements.builderFields, currentLayerSuggestions());
  } catch (error) {
    state.reports = null;
    resetReview(elements, "Review failed; no canonical evidence is current.");
    disablePreflightUntilReview("Fix and review the Workflow before running Preflight.");
    setRequestStatus(elements.requestStatus, error.message, true);
    setReviewState(elements.reviewState, "Review failed", true);
  } finally {
    elements.reviewButton.disabled = false;
  }
}

function recordPreflightDraft(event) {
  const control = event.target;
  if (!control || !control.dataset || !control.dataset.preflightLayer) {
    return;
  }
  const hadCurrentPreflight = state.preflight !== null;
  state.layerDrafts[control.dataset.preflightLayer] = control.value;
  state.preflight = null;
  resetPreflightResult(
    elements.preflightResult,
    hadCurrentPreflight
      ? "Inline data changed. Run Preflight again for current evidence."
      : "Inline data is ready for canonical Preflight.",
  );
  setRequestStatus(
    elements.preflightStatus,
    hadCurrentPreflight
      ? "Inline data changed; Preflight evidence is stale."
      : "Inline data changed; run canonical Preflight when ready.",
  );
}

async function runPreflight() {
  if (!state.reports) {
    setRequestStatus(elements.preflightStatus, "Review the current Workflow before Preflight.", true);
    return;
  }

  elements.preflightButton.disabled = true;
  setRequestStatus(elements.preflightStatus, "Running canonical Preflight…");

  try {
    const request = buildPreflightRequest(
      parseWorkflow(),
      state.reports,
      state.layerDrafts,
    );
    const report = await requestJson(ENDPOINTS.preflight, {
      method: "POST",
      body: request,
    });
    assertPreflightEvidenceChain(report, state.reports);
    state.preflight = report;
    renderPreflightReport(elements.preflightResult, report);
    setRequestStatus(
      elements.preflightStatus,
      report.valid
        ? "Canonical Preflight passed for the supplied inline layers."
        : "Canonical Preflight completed with findings.",
      !report.valid,
    );
  } catch (error) {
    state.preflight = null;
    resetPreflightResult(elements.preflightResult, "Preflight did not produce current evidence.");
    setRequestStatus(elements.preflightStatus, error.message, true);
  } finally {
    elements.preflightButton.disabled = requiredLayerNames(state.reports).length === 0;
  }
}

elements.reviewButton.addEventListener("click", reviewWorkflow);
elements.builderOperator.addEventListener("change", renderSelectedOperator);
elements.addStepButton.addEventListener("click", insertDraftStep);
elements.workflow.addEventListener("input", () => invalidateReview());
elements.layerNames.addEventListener("input", () => invalidateReview());
elements.preflightInputs.addEventListener("input", recordPreflightDraft);
elements.preflightButton.addEventListener("click", runPreflight);

initializeTabs();
loadServiceMetadata();
