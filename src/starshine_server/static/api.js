export const ENDPOINTS = Object.freeze({
  health: "/healthz",
  operators: "/api/v1/operators",
  validate: "/api/v1/workflows/validate",
  plan: "/api/v1/workflows/plan",
  contract: "/api/v1/workflows/contract",
  graph: "/api/v1/workflows/graph",
  explain: "/api/v1/workflows/explain",
});

// Keep exact response text separate from convenience objects and their lifetime.
const responseTexts = new WeakMap();

export function responseJsonText(payload) {
  return responseTexts.get(payload);
}

function workflowRequestBody(raw, layerNames = []) {
  if (typeof raw !== "string") {
    throw new Error("Workflow JSON must be text.");
  }
  if (!Array.isArray(layerNames) || layerNames.some((name) => typeof name !== "string")) {
    throw new Error("Layer names must be an array of strings.");
  }
  let workflow;
  try {
    workflow = JSON.parse(raw);
  } catch (error) {
    throw new Error(`Workflow JSON is not valid: ${error.message}`);
  }
  if (!workflow || typeof workflow !== "object" || Array.isArray(workflow)) {
    throw new Error("Workflow JSON must be an object.");
  }
  // Parsing checks syntax/root shape only. Reserializing would change numeric
  // values and Core validation (for example 8.0, -0.0, large integers, 1e400).
  return `{"workflow":${raw},"layer_names":${JSON.stringify(layerNames)}}`;
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

export async function requestJson(path, options = {}) {
  const init = {
    method: options.method || "GET",
    headers: {
      accept: "application/json",
    },
    credentials: "same-origin",
  };

  if (options.workflowText !== undefined) {
    init.headers["content-type"] = "application/json";
    init.body = workflowRequestBody(options.workflowText, options.layerNames);
  } else if (options.body !== undefined) {
    init.headers["content-type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }

  const response = await fetch(path, init);
  let payload = null;
  let raw;
  try {
    raw = await response.text();
    payload = JSON.parse(raw);
  } catch {
    throw new Error(`Server returned non-JSON content for ${path}.`);
  }

  if (!response.ok) {
    throw new Error(apiErrorMessage(payload, response.status));
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`Server returned an invalid JSON object for ${path}.`);
  }
  responseTexts.set(payload, raw);
  return payload;
}
