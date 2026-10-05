export function requiredLayerNames(reviewReports) {
  const plan = reviewReports && reviewReports.plan;
  if (!plan || !Array.isArray(plan.required_external_layers)) {
    return [];
  }
  return plan.required_external_layers.filter((name) => typeof name === "string" && name.length > 0);
}

export function parseLayerDrafts(layerNames, drafts) {
  const layers = {};
  for (const name of Array.isArray(layerNames) ? layerNames : []) {
    if (typeof name !== "string" || !name) {
      continue;
    }
    const raw = drafts && typeof drafts[name] === "string" ? drafts[name].trim() : "";
    if (!raw) {
      continue;
    }

    try {
      layers[name] = JSON.parse(raw);
    } catch (error) {
      throw new Error(`Layer "${name}" is not valid JSON: ${error.message}`);
    }
  }
  return layers;
}

export function buildPreflightRequest(workflow, reviewReports, drafts) {
  const names = requiredLayerNames(reviewReports);
  const layers = parseLayerDrafts(names, drafts);
  if (Object.keys(layers).length === 0) {
    throw new Error("Paste JSON for at least one required layer before running Preflight.");
  }
  return { workflow, layers };
}

export function assertPreflightEvidenceChain(preflight, reviewReports) {
  const planDigest = reviewReports && reviewReports.plan && reviewReports.plan.plan_digest;
  const contractDigest =
    reviewReports && reviewReports.contract && reviewReports.contract.contract_digest;

  if (
    !preflight ||
    preflight.plan_digest !== planDigest ||
    preflight.contract_digest !== contractDigest
  ) {
    throw new Error("Preflight evidence does not match the current canonical review.");
  }
}
