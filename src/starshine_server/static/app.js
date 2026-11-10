import {
  appendDraftStep, buildDraftStep, findCatalogOperator, layerSuggestions, parseDraftJson,
} from "./editor.js";
import {
  populateOperatorSelect, renderStepBuilder, updateLayerSuggestions,
} from "./render_editor.js";
import { ENDPOINTS, requestJson, responseJsonText } from "./api.js";
import { buildPreflightRequest, assertPreflightEvidence, unusedLayerNames } from "./assurance.js";
import {
  renderPreflightBindings, renderPreflightLimits, renderPreflightReport,
} from "./render_preflight.js";
import {
  initializeTabs,
  renderCatalog,
  renderReports,
  setRequestStatus,
  setReviewState,
} from "./render.js";

const state = {
  catalog: null,
  reports: null,
  // A response may update the page only while it owns the latest review request.
  reviewRequestId: 0,
  preflightRequestId: 0,
  preflightPending: false,
  workflowText: null,
  layerDrafts: new Map(),
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
  preflightButton: document.querySelector("#preflight-button"),
  preflightStatus: document.querySelector("#preflight-status"),
  preflightBindings: document.querySelector("#preflight-bindings"),
  preflightContent: document.querySelector("#preflight-content"),
  preflightLimits: document.querySelector("#preflight-limits"),
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
  const inputs = Object.create(null);
  const parameters = Object.create(null);

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

function insertDraftStep() {
  try {
    const workflow = parseDraftJson(elements.workflow.value, "Workflow JSON");
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

    invalidateReview();
    setRequestStatus(elements.requestStatus, "Unvalidated draft inserted. Review again for current evidence.");
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
    populateOperatorSelect(elements.builderOperator, null, "Catalog unavailable");
    elements.addStepButton.disabled = true;
    setRequestStatus(elements.builderStatus, "Catalog unavailable; assisted editing is disabled.", true);
    setRequestStatus(elements.requestStatus, error.message, true);
    setReviewState(elements.reviewState, "Server unavailable", true);
  }
}

async function loadPreflightLimits() {
  try {
    renderPreflightLimits(elements.preflightLimits, await requestJson(ENDPOINTS.limits));
  } catch (error) {
    setRequestStatus(elements.preflightLimits, `Limits unavailable: ${error.message}`, true);
  }
}

function updatePreflightButton() {
  elements.preflightButton.disabled = !state.reports || state.preflightPending ||
    unusedLayerNames(state.reports).length > 0;
}

function invalidatePreflight() {
  state.preflightRequestId += 1;
  state.preflightPending = false;
  renderPreflightReport(elements.preflightContent, null);
  setRequestStatus(elements.preflightStatus, state.reports
    ? "Data changed. Run Preflight for current evidence."
    : "Review the Workflow before running Preflight.");
  updatePreflightButton();
}

function renderBindings() {
  renderPreflightBindings(elements.preflightBindings, state.reports, state.layerDrafts,
    (name, raw) => {
      state.layerDrafts.set(name, raw);
      invalidatePreflight();
    });
}

async function runPreflight() {
  invalidatePreflight();
  const requestId = state.preflightRequestId;
  state.preflightPending = true;
  updatePreflightButton();
  setRequestStatus(elements.preflightStatus, "Sending inline data for canonical Preflight…");
  try {
    const request = buildPreflightRequest(state.workflowText, state.reports, state.layerDrafts);
    const report = await requestJson(ENDPOINTS.preflight, request);
    if (requestId !== state.preflightRequestId) return;
    assertPreflightEvidence(report, state.reports);
    renderPreflightReport(elements.preflightContent, report, responseJsonText(report));
    setRequestStatus(elements.preflightStatus,
      report.valid ? "Canonical Preflight complete: PASS." : "Canonical Preflight complete: FAIL.",
      !report.valid);
  } catch (error) {
    if (requestId !== state.preflightRequestId) return;
    setRequestStatus(elements.preflightStatus,
      `Preflight request failed; no current evidence. ${error.message}`, true);
  } finally {
    if (requestId === state.preflightRequestId) {
      state.preflightPending = false;
      updatePreflightButton();
    }
  }
}

function invalidateReview() {
  state.reviewRequestId += 1;
  state.reports = null;
  state.workflowText = null;
  invalidatePreflight();
  renderBindings();
  renderReports(elements, null);
  // The invalidated request no longer owns the button's disabled state.
  elements.reviewButton.disabled = false;
  setRequestStatus(elements.requestStatus, "Inputs changed. Review again for current evidence.");
  setReviewState(elements.reviewState, "Not reviewed");
  updateLayerSuggestions(elements.builderFields, currentLayerSuggestions());
}

async function reviewWorkflow() {
  const requestId = ++state.reviewRequestId;
  state.reports = null;
  state.workflowText = null;
  invalidatePreflight();
  renderBindings();
  renderReports(elements, null);
  elements.reviewButton.disabled = true;
  setRequestStatus(elements.requestStatus, "Validating workflow…");
  setReviewState(elements.reviewState, "Reviewing");

  try {
    const request = {
      method: "POST",
      workflowText: elements.workflow.value,
      layerNames: parseLayerNames(),
    };

    const validation = await requestJson(ENDPOINTS.validate, request);
    if (requestId !== state.reviewRequestId) return;

    setRequestStatus(elements.requestStatus, "Building canonical review reports…");
    const [plan, contract, graph, explain] = await Promise.all([
      requestJson(ENDPOINTS.plan, request),
      requestJson(ENDPOINTS.contract, request),
      requestJson(ENDPOINTS.graph, request),
      requestJson(ENDPOINTS.explain, request),
    ]);

    if (requestId !== state.reviewRequestId) return;
    assertEvidenceChain(plan, contract, graph, explain);
    state.reports = { validation, plan, contract, graph, explain };
    state.workflowText = request.workflowText;
    renderBindings();
    updatePreflightButton();
    setRequestStatus(elements.preflightStatus, unusedLayerNames(state.reports).length
      ? "Remove unused external layer declarations and Review again before Preflight."
      : "Paste required layers, then explicitly run Preflight. Blank slots are omitted; missing inputs may fail at the Server boundary.");
    renderReports(elements, state.reports);
    setRequestStatus(elements.requestStatus, "Canonical review complete.");
    setReviewState(elements.reviewState, "Reviewed");
  } catch (error) {
    if (requestId !== state.reviewRequestId) return;
    setRequestStatus(elements.requestStatus, error.message, true);
    setReviewState(elements.reviewState, "Review failed", true);
  } finally {
    if (requestId === state.reviewRequestId) {
      elements.reviewButton.disabled = false;
    }
  }
}

elements.workflow.addEventListener("input", invalidateReview);
elements.layerNames.addEventListener("input", invalidateReview);
elements.reviewButton.addEventListener("click", reviewWorkflow);
elements.builderOperator.addEventListener("change", renderSelectedOperator);
elements.addStepButton.addEventListener("click", insertDraftStep);
elements.preflightButton.addEventListener("click", runPreflight);
initializeTabs();
updatePreflightButton();
loadServiceMetadata();
loadPreflightLimits();
