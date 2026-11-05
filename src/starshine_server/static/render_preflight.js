import { clearNode, textElement } from "./render.js";

export function renderPreflightBindings(container, reports, drafts, onChange) {
  clearNode(container);
  const names = reports?.plan?.required_external_layers || [];
  const required = new Set(names);
  if (!reports) {
    container.appendChild(textElement("p", "Review the Workflow to create required layer slots.", "muted"));
  }
  const unused = reports?.plan?.unused_external_layers || [];
  if (unused.length) {
    container.appendChild(textElement("p",
      `Remove unused external layer declarations (${unused.join(", ")}) and Review again before Preflight. No substitute data will be created.`,
      "boundary-note"));
  }
  for (const [index, name] of names.entries()) {
    const card = textElement("article", "", "report-card");
    const label = textElement("label", `Layer: ${name}`);
    const id = `preflight-layer-${index}`;
    label.setAttribute("for", id);
    card.appendChild(label);
    const contract = reports.contract.layers?.find((layer) => layer.name === name);
    if (contract) {
      const details = textElement("details", "");
      details.appendChild(textElement("summary", "Canonical preparation requirements"));
      details.appendChild(textElement("pre", JSON.stringify(contract, null, 2), "raw-block"));
      card.appendChild(details);
    }
    const input = document.createElement("textarea");
    input.id = id;
    input.className = "layer-editor preflight-editor";
    input.spellcheck = false;
    input.dataset.layerName = name;
    input.value = drafts.get(name) ?? "";
    input.addEventListener("input", () => onChange(name, input.value));
    card.appendChild(input);
    container.appendChild(card);
  }
  for (const [name, raw] of drafts) {
    if (required.has(name)) continue;
    const card = textElement("article", "", "report-card");
    const label = textElement("label", `Retained unbound draft: ${name}`);
    const input = document.createElement("textarea");
    // Wrapping label avoids deriving a DOM identifier from an arbitrary layer key.
    input.className = "layer-editor preflight-editor";
    input.readOnly = true;
    input.value = raw;
    label.appendChild(input);
    card.appendChild(label);
    card.appendChild(textElement("p",
      "Kept in this page's memory, not sent. A later Review requiring this exact name will restore it."));
    container.appendChild(card);
  }
}

export function renderPreflightLimits(container, limits) {
  clearNode(container);
  container.appendChild(textElement("p",
    "Server-enforced inline limits (information only). Preflight is synchronous and is not isolated by the execution worker supervisor.", "muted"));
  container.appendChild(textElement("pre", JSON.stringify(limits.inline_preflight, null, 2), "raw-block"));
}

export function renderPreflightReport(container, report, raw) {
  clearNode(container);
  if (!report) {
    container.appendChild(textElement("p", "No current Preflight evidence. Run Preflight after Review.", "muted"));
    return;
  }
  container.appendChild(textElement("h3", report.valid ? "PASS" : "FAIL"));
  container.appendChild(textElement("p",
    `Checked layers: ${report.checked_layer_count} / ${report.layer_count}; errors: ${report.error_count}; warnings: ${report.warning_count}.`));
  container.appendChild(textElement("p", "PASS does not guarantee execution success. No workflow is executed by this screen.", "boundary-note"));
  for (const layer of report.layers || []) {
    const card = textElement("article", "", "report-card");
    card.appendChild(textElement("h3", `${layer.name}: ${layer.status}`));
    card.appendChild(textElement("p", `Features: ${layer.feature_count ?? "not reported"}; declared CRS: ${layer.declared_crs ?? "not reported"}`));
    card.appendChild(textElement("p", `Geometry counts: ${JSON.stringify(layer.geometry_counts)}`));
    container.appendChild(card);
  }
  container.appendChild(textElement("h3", "Canonical findings"));
  for (const finding of report.findings || []) {
    const card = textElement("article", "", "report-card");
    card.appendChild(textElement("h4", `${finding.severity}: ${finding.code}`));
    card.appendChild(textElement("p", finding.message));
    card.appendChild(textElement("p", `Layer: ${finding.layer}; occurrences: ${finding.occurrence_count}`));
    container.appendChild(card);
  }
  if (!report.findings?.length) container.appendChild(textElement("p", "No findings reported."));
  container.appendChild(textElement("h3", "Remaining checks"));
  const checks = textElement("ul", "", "report-list");
  for (const check of report.remaining_checks || []) checks.appendChild(textElement("li", check));
  container.appendChild(checks);
  for (const name of ["workflow_digest", "plan_digest", "contract_digest", "preflight_digest"]) {
    container.appendChild(textElement("p", `${name}: ${report[name]}`, "preflight-digest"));
  }
  container.appendChild(textElement("h3", "Exact Server Preflight JSON"));
  container.appendChild(textElement("p", "Summaries may normalize numeric spelling. The original response below is preserved without reserialization.", "muted"));
  container.appendChild(textElement("pre", raw ?? "Original response unavailable.", "raw-block"));
}
