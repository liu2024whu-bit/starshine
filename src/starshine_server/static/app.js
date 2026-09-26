import { initializeStepComposer } from "./composer.js";
import { ENDPOINTS, requestJson } from "./api.js";
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
  composerOperator: document.querySelector("#composer-operator"),
  composerDetails: document.querySelector("#composer-details"),
  composerFields: document.querySelector("#composer-fields"),
  composerOutput: document.querySelector("#composer-output"),
  composerStatus: document.querySelector("#composer-status"),
  composerAdd: document.querySelector("#composer-add"),
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

function appendWorkflowStep(step) {
  const workflow = parseWorkflow();
  if (!Array.isArray(workflow.steps)) {
    throw new Error("Workflow JSON must contain a steps array before the composer can add a step.");
  }
  workflow.steps.push(step);
  elements.workflow.value = JSON.stringify(workflow, null, 2);
  state.reports = null;
  setReviewState(elements.reviewState, "Not reviewed");
  setRequestStatus(
    elements.requestStatus,
    "Workflow changed. Run canonical review before treating it as valid.",
  );
}

function parseLayerNames() {
  return elements.layerNames.value
    .split(/\r?\n/)
    .map((value) => value.trim())
    .filter((value) => value.length > 0);
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

async function loadServiceMetadata() {
  try {
    const [health, catalog] = await Promise.all([
      requestJson(ENDPOINTS.health),
      requestJson(ENDPOINTS.operators),
    ]);
    state.catalog = catalog;
    renderCatalog(elements.operatorCatalog, elements.catalogStatus, catalog);
    initializeStepComposer({
      catalog,
      select: elements.composerOperator,
      details: elements.composerDetails,
      fields: elements.composerFields,
      output: elements.composerOutput,
      status: elements.composerStatus,
      addButton: elements.composerAdd,
      onAdd: appendWorkflowStep,
    });
    const version = health.core_version || "unknown";
    elements.serverVersion.textContent = `Core ${version}`;
  } catch (error) {
    elements.catalogStatus.textContent = "Catalog unavailable";
    setRequestStatus(elements.requestStatus, error.message, true);
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
  } catch (error) {
    setRequestStatus(elements.requestStatus, error.message, true);
    setReviewState(elements.reviewState, "Review failed", true);
  } finally {
    elements.reviewButton.disabled = false;
  }
}

elements.reviewButton.addEventListener("click", reviewWorkflow);
initializeTabs();
loadServiceMetadata();
