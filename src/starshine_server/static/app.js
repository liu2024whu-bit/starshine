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
  // A response may update the page only while it owns the latest review request.
  reviewRequestId: 0,
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
    const version = health.core_version || "unknown";
    elements.serverVersion.textContent = `Core ${version}`;
  } catch (error) {
    elements.catalogStatus.textContent = "Catalog unavailable";
    setRequestStatus(elements.requestStatus, error.message, true);
    setReviewState(elements.reviewState, "Server unavailable", true);
  }
}

function invalidateReview() {
  state.reviewRequestId += 1;
  state.reports = null;
  renderReports(elements, null);
  // The invalidated request no longer owns the button's disabled state.
  elements.reviewButton.disabled = false;
  setReviewState(elements.reviewState, "Not reviewed");
}

async function reviewWorkflow() {
  const requestId = ++state.reviewRequestId;
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
    if (requestId !== state.reviewRequestId) return;

    setRequestStatus(elements.requestStatus, "Building canonical review reports…");
    const [plan, contract, graph, explain] = await Promise.all([
      requestJson(ENDPOINTS.plan, { method: "POST", body: request }),
      requestJson(ENDPOINTS.contract, { method: "POST", body: request }),
      requestJson(ENDPOINTS.graph, { method: "POST", body: request }),
      requestJson(ENDPOINTS.explain, { method: "POST", body: request }),
    ]);

    if (requestId !== state.reviewRequestId) return;
    assertEvidenceChain(plan, contract, graph, explain);
    state.reports = { validation, plan, contract, graph, explain };
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
initializeTabs();
loadServiceMetadata();
