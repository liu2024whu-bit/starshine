// Transport syntax and evidence continuity only. Core owns all data semantics.
export function requiredLayerNames(reports) {
  return reports?.plan?.required_external_layers || [];
}

export function unusedLayerNames(reports) {
  return reports?.plan?.unused_external_layers || [];
}

export function buildPreflightRequest(workflowText, reports, drafts) {
  if (!reports) throw new Error("Review the Workflow before running Preflight.");
  if (unusedLayerNames(reports).length) {
    throw new Error("Remove unused external layer declarations and Review again before Preflight.");
  }
  const layerTexts = [];
  for (const name of requiredLayerNames(reports)) {
    const raw = drafts.get(name) ?? "";
    if (!raw.trim()) continue;
    try {
      JSON.parse(raw);
    } catch (error) {
      throw new Error(`Layer ${JSON.stringify(name)} is not valid JSON: ${error.message}`);
    }
    // Preserve the original tokens. Parsing here is syntax-only, not rewriting.
    layerTexts.push([name, raw]);
  }
  return { method: "POST", workflowText, layerTexts };
}

export function assertPreflightEvidence(report, reports) {
  if (!reports ||
    typeof report.plan_digest !== "string" ||
    typeof report.contract_digest !== "string" ||
    typeof report.workflow_digest !== "string" ||
    report.plan_digest !== reports.plan.plan_digest ||
    report.contract_digest !== reports.contract.contract_digest ||
    report.workflow_digest !== reports.plan.workflow_digest
  ) {
    throw new Error("Preflight does not match the current canonical Review evidence chain. Review again.");
  }
}
