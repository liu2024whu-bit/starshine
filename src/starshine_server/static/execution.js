function sameJson(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

export function terminalOutputNames(reviewReports) {
  const plan = reviewReports && reviewReports.plan;
  if (!plan || !Array.isArray(plan.terminal_layers)) {
    return [];
  }
  return plan.terminal_layers.filter((name) => typeof name === "string" && name.length > 0);
}

export function buildExecutionRequest(preflightRequest, outputLayer) {
  if (
    !preflightRequest ||
    typeof preflightRequest !== "object" ||
    !preflightRequest.workflow ||
    typeof preflightRequest.workflow !== "object" ||
    !preflightRequest.layers ||
    typeof preflightRequest.layers !== "object"
  ) {
    throw new Error("Current Preflight request evidence is unavailable.");
  }
  if (typeof outputLayer !== "string" || !outputLayer) {
    throw new Error("Choose a canonical terminal output before execution.");
  }

  return {
    workflow: preflightRequest.workflow,
    layers: preflightRequest.layers,
    output_layer: outputLayer,
  };
}

export function assertExecutionEvidenceChain(
  execution,
  currentPreflight,
  expectedOutputLayer,
  executionPolicy,
) {
  if (!currentPreflight || currentPreflight.valid !== true) {
    throw new Error("Execution requires a current passing canonical Preflight.");
  }
  if (!execution || execution.status !== "succeeded") {
    throw new Error("Server execution did not report success.");
  }
  if (execution.output_layer !== expectedOutputLayer) {
    throw new Error("Execution returned a different output layer than requested.");
  }

  const returnedPreflight = execution.preflight;
  if (
    !returnedPreflight ||
    returnedPreflight.valid !== true ||
    returnedPreflight.preflight_digest !== currentPreflight.preflight_digest ||
    returnedPreflight.plan_digest !== currentPreflight.plan_digest ||
    returnedPreflight.contract_digest !== currentPreflight.contract_digest
  ) {
    throw new Error("Execution Preflight evidence is stale or does not match the current review.");
  }

  if (!sameJson(execution.execution_policy, executionPolicy)) {
    throw new Error("Execution policy changed after limits discovery.");
  }
  if (!execution.result || typeof execution.result !== "object" || Array.isArray(execution.result)) {
    throw new Error("Execution response omitted the canonical result object.");
  }
  if (
    !execution.manifest ||
    typeof execution.manifest !== "object" ||
    Array.isArray(execution.manifest)
  ) {
    throw new Error("Execution response omitted the canonical reproducibility manifest.");
  }
}
