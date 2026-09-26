import { assertPreflightMatchesReview, parseNamedLayers } from "./assurance.js";
import { initializeStepComposer } from "./composer.js";
import { ENDPOINTS, requestJson } from "./api.js";
import {
  initializeTabs,
  renderAssumptions,
  renderCatalog,
  renderEvidence,
  renderPreflight,
  renderReports,
  setRequestStatus,
  setReviewState,
} from "./render.js";

const state = {
  catalog: null,
  limits: null,
  reports: null,
  reviewFresh: false,
  preflight: null,
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
  preflightLayers: document.querySelector("#preflight-layers"),
  preflightButton: document.querySelector("#preflight-button"),
  preflightStatus: document.querySelector("#preflight-status"),
  preflightLimits: document.querySelector("#preflight-limits"),
  overview: document.querySelector("#overview-content"),
  contract: document.querySelector("#contract-content"),
  graph: document.querySelector("#graph-content"),
  explain: document.querySelector("#explain-content"),
  assumptions: document.querySelector("#assumptions-content"),
  preflight: document.querySelector("#preflight-content"),
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

function refreshAssumptions() {
  renderAssumptions(
    elements.assumptions,
    state.reports,
    state.preflight,
    state.reviewFresh,
  );
}

function clearPreflight(message) {
  state.preflight = null;
  renderPreflight(elements.preflight, null);
  refreshAssumptions();
  elements.preflightStatus.textContent = message;
}

function markReviewStale(message) {
  state.reviewFresh = false;
  elements.preflightButton.disabled = true;
  setReviewState(elements.reviewState, "Stale");
  setRequestStatus(elements.requestStatus, message);
  clearPreflight("Workflow review changed. Complete a fresh review before Preflight.");
}

function formatPreflightLimits(limits) {
  if (!limits || typeof limits !== "object") {
    return "Server inline Preflight limits are unavailable.";
  }
  return [
    `${limits.max_request_bytes} request bytes`,
    `${limits.max_layers} layers`,
    `${limits.max_workflow_steps} Workflow steps`,
    `${limits.max_features_per_layer} features/layer`,
    `${limits.max_total_features} total features`,
  ].join(" · ");
}

function appendWorkflowStep(step) {
  const workflow = parseWorkflow();
  if (!Array.isArray(workflow.steps)) {
    throw new Error("Workflow JSON must contain a steps array before the composer can add a step.");
  }
  workflow.steps.push(step);
  elements.workflow.value = JSON.stringify(workflow, null, 2);
  markReviewStale("Workflow changed. Run canonical review before treating it as valid.");
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
    const [health, catalog, limits] = await Promise.all([
      requestJson(ENDPOINTS.health),
      requestJson(ENDPOINTS.operators),
      requestJson(ENDPOINTS.limits),
    ]);
    state.catalog = catalog;
    state.limits = limits;
    elements.preflightLimits.textContent = formatPreflightLimits(limits.inline_preflight);
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
    state.reviewFresh = true;
    renderReports(elements, state.reports);
    clearPreflight("Fresh review complete. Inline GeoJSON can now be checked.");
    elements.preflightButton.disabled = false;
    setRequestStatus(elements.requestStatus, "Canonical review complete.");
    setReviewState(elements.reviewState, "Reviewed");
  } catch (error) {
    setRequestStatus(elements.requestStatus, error.message, true);
    setReviewState(elements.reviewState, "Review failed", true);
  } finally {
    elements.reviewButton.disabled = false;
  }
}

async function runPreflight() {
  if (!state.reviewFresh || !state.reports) {
    setRequestStatus(
      elements.preflightStatus,
      "A fresh canonical Workflow review is required before Preflight.",
      true,
    );
    return;
  }

  elements.preflightButton.disabled = true;
  setRequestStatus(elements.preflightStatus, "Running canonical Preflight…");

  try {
    const layers = parseNamedLayers(elements.preflightLayers.value);
    const workflow = parseWorkflow();
    const report = await requestJson(ENDPOINTS.preflight, {
      method: "POST",
      body: { workflow, layers },
    });

    assertPreflightMatchesReview(state.reports, report);
    state.preflight = report;
    renderPreflight(elements.preflight, report);
    refreshAssumptions();
    renderEvidence(elements.evidence, { ...state.reports, preflight: report });
    setRequestStatus(
      elements.preflightStatus,
      report.valid
        ? "Canonical Preflight completed without errors."
        : "Canonical Preflight completed with findings.",
      !report.valid,
    );
  } catch (error) {
    state.preflight = null;
    renderPreflight(elements.preflight, null);
    setRequestStatus(elements.preflightStatus, error.message, true);
  } finally {
    elements.preflightButton.disabled = !state.reviewFresh;
  }
}

function onReviewedInputChanged() {
  markReviewStale("Workflow or external layer names changed. Review evidence is now stale.");
}

function onPreflightDataChanged() {
  if (state.preflight) {
    clearPreflight("Inline layer data changed. Run Preflight again; Workflow review remains fresh.");
  }
}

elements.reviewButton.addEventListener("click", reviewWorkflow);
elements.preflightButton.addEventListener("click", runPreflight);
elements.workflow.addEventListener("input", onReviewedInputChanged);
elements.layerNames.addEventListener("input", onReviewedInputChanged);
elements.preflightLayers.addEventListener("input", onPreflightDataChanged);
initializeTabs();
loadServiceMetadata();
