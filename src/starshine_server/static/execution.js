function sameJson(left, right) {
  if (Object.is(left, right)) {
    return true;
  }
  if (Array.isArray(left) || Array.isArray(right)) {
    return (
      Array.isArray(left) &&
      Array.isArray(right) &&
      left.length === right.length &&
      left.every((value, index) => sameJson(value, right[index]))
    );
  }
  if (
    left &&
    right &&
    typeof left === "object" &&
    typeof right === "object"
  ) {
    const leftKeys = Object.keys(left).sort();
    const rightKeys = Object.keys(right).sort();
    return (
      leftKeys.length === rightKeys.length &&
      leftKeys.every(
        (key, index) =>
          key === rightKeys[index] &&
          sameJson(left[key], right[key]),
      )
    );
  }
  return false;
}

export function terminalOutputNames(reviewReports) {
  const plan = reviewReports && reviewReports.plan;
  if (!plan || !Array.isArray(plan.terminal_layers)) {
    return [];
  }
  return plan.terminal_layers.filter((name) => typeof name === "string" && name.length > 0);
}

export function buildExecutionRequest(preflightRequest, outputLayer, terminalOutputs) {
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
  if (!Array.isArray(terminalOutputs) || !terminalOutputs.includes(outputLayer)) {
    throw new Error("Execution output must be one of the current canonical terminal layers.");
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
