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
  execute: "/api/v1/workflows/execute",
});

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

  if (options.body !== undefined) {
    init.headers["content-type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }

  const response = await fetch(path, init);
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    throw new Error(`Server returned non-JSON content for ${path}.`);
  }

  if (!response.ok) {
    throw new Error(apiErrorMessage(payload, response.status));
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`Server returned an invalid JSON object for ${path}.`);
  }
  return payload;
}
