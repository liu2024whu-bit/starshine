export const ENDPOINTS = Object.freeze({
  health: "/healthz",
  operators: "/api/v1/operators",
  limits: "/api/v1/limits",
  validate: "/api/v1/workflows/validate",
  plan: "/api/v1/workflows/plan",
  contract: "/api/v1/workflows/contract",
  graph: "/api/v1/workflows/graph",
  explain: "/api/v1/workflows/explain",
  preflight: "/api/v1/workflows/preflight",
});

// Keep exact response text separate from convenience objects and their lifetime.
const responseTexts = new WeakMap();

export function responseJsonText(payload) {
  return responseTexts.get(payload);
}

function workflowRequestBody(raw, layerNames = [], layerTexts) {
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
  if (layerTexts !== undefined) {
    if (!Array.isArray(layerTexts)) throw new Error("Layer drafts must be named JSON texts.");
    const seen = new Set();
    const entries = layerTexts.map((entry) => {
      if (!Array.isArray(entry) || entry.length !== 2 ||
        typeof entry[0] !== "string" || typeof entry[1] !== "string" || seen.has(entry[0])) {
        throw new Error("Layer drafts must have unique names and JSON text values.");
      }
      const [name, text] = entry;
      seen.add(name);
      JSON.parse(text); // Syntax only. Do not reserialize the parsed value.
      return `${JSON.stringify(name)}:${text}`;
    });
    return `{"workflow":${raw},"layers":{${entries.join(",")}}}`;
  }
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
    init.body = workflowRequestBody(options.workflowText, options.layerNames, options.layerTexts);
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
