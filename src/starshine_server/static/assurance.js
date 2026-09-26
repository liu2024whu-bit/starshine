export function parseNamedLayers(rawText) {
  let value;
  try {
    value = JSON.parse(rawText);
  } catch (error) {
    throw new Error(`Inline layers JSON is not valid: ${error.message}`);
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Inline layers JSON must be one object keyed by logical layer name.");
  }
  return value;
}

export function assertPreflightMatchesReview(reports, preflight) {
  if (!reports || !reports.plan || !reports.contract) {
    throw new Error("A fresh canonical Workflow review is required before Preflight.");
  }

  const mismatches = [];
  if (preflight.workflow_digest !== reports.plan.workflow_digest) {
    mismatches.push("workflow");
  }
  if (preflight.plan_digest !== reports.plan.plan_digest) {
    mismatches.push("plan");
  }
  if (preflight.contract_digest !== reports.contract.contract_digest) {
    mismatches.push("contract");
  }

  if (mismatches.length) {
    throw new Error(
      `Preflight evidence does not match the current reviewed ${mismatches.join(", ")} digest(s).`,
    );
  }
}
