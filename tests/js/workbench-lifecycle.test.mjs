import assert from "node:assert/strict";
import test, { after } from "node:test";
import { copyFileSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

// A temporary package marks exact, unmodified asset copies as ES modules on Node 18+.
const moduleDirectory = mkdtempSync(join(tmpdir(), "starshine-workbench-test-"));
writeFileSync(join(moduleDirectory, "package.json"), '{"type":"module"}');
for (const name of ["app.js", "api.js", "render.js", "editor.js", "render_editor.js",
  "assurance.js", "render_preflight.js"]) {
  copyFileSync(new URL(`../../src/starshine_server/static/${name}`, import.meta.url), join(moduleDirectory, name));
}
after(() => rmSync(moduleDirectory, { recursive: true, force: true }));

// Exercise the shipped modules with an in-memory DOM and controlled HTTP replies.
// This checks request ownership and rendered evidence, not browser layout or CSP.
class Element {
  constructor(tag = "div") { this.tagName = tag.toUpperCase(); }
  children = [];
  dataset = {};
  attributes = {};
  listeners = new Map();
  disabled = false;
  readOnly = false;
  value = "";
  ownText = "";
  classes = new Set();
  classList = {
    toggle: (name, enabled) => enabled ? this.classes.add(name) : this.classes.delete(name),
    contains: (name) => this.classes.has(name),
  };
  get firstChild() { return this.children[0] || null; }
  get textContent() { return this.ownText + this.children.map((child) => child.textContent).join(""); }
  set textContent(value) { this.ownText = String(value); this.children = []; }
  appendChild(child) { this.children.push(child); return child; }
  removeChild(child) { this.children.splice(this.children.indexOf(child), 1); }
  addEventListener(name, listener) { this.listeners.set(name, listener); }
  setAttribute(name, value) { this.attributes[name] = value; }
  querySelectorAll(selector) {
    const matches = (element) => selector.startsWith("#")
      ? element.id === selector.slice(1)
      : selector.startsWith("[data-")
        ? Object.hasOwn(element.dataset, selector.slice(6, -1).replace(/-([a-z])/g, (_, c) => c.toUpperCase()))
        : element.tagName === selector.toUpperCase();
    return this.children.flatMap((child) => [ ...(matches(child) ? [child] : []), ...child.querySelectorAll(selector)]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  dispatch(name) { return this.listeners.get(name)?.({ target: this, currentTarget: this }); }
}

let instance = 0;
const catalog = { operators: [{ name: "synthetic_operator", summary: "Synthetic operation",
  inputs: [{ name: "source", contract: { geometry_types: ["Point"], crs: { mode: "parameter" },
    required_fields: [{ parameter: "field" }], written_fields: [{ name: "result" }], notes: ["Unresolved note"] } }],
  parameters: [{ name: "amount", required: true, schema: { type: "number" } },
    { name: "optional", default: false, schema: { type: "boolean" } }],
}] };
const limits = { inline_preflight: { max_request_bytes: 1048576, max_json_depth: 64,
  max_layers: 20, max_layer_name_chars: 100, max_workflow_steps: 100,
  max_features_per_layer: 10000, max_total_features: 20000 } };
async function setup({ catalogUnavailable = false, limitsUnavailable = false } = {}) {
  const elements = new Map();
  globalThis.document = {
    querySelector(selector) {
      if (!elements.has(selector)) elements.set(selector, new Element());
      return elements.get(selector);
    },
    querySelectorAll() { return []; },
    createElement(tag) { return new Element(tag); },
  };
  document.querySelector("#builder-operator").disabled = true;
  const loadingOption = document.createElement("option");
  loadingOption.textContent = "Loading canonical catalog…";
  document.querySelector("#builder-operator").appendChild(loadingOption);
  document.querySelector("#add-step-button").disabled = true;
  // Match the static page's initial evidence placeholder, before app.js runs.
  const preflightPlaceholder = document.createElement("p");
  preflightPlaceholder.textContent = "No current Preflight evidence. Run Preflight after Review.";
  document.querySelector("#preflight-content").appendChild(preflightPlaceholder);
  const requests = [];
  const metadataRequests = [];
  globalThis.fetch = (path, init) => {
    if (["/healthz", "/api/v1/operators", "/api/v1/limits"].includes(path)) {
      metadataRequests.push({ path, init });
      if (path === "/healthz") return Promise.resolve(reply({ core_version: "test" }));
      if (path === "/api/v1/limits") return Promise.resolve(
        limitsUnavailable ? reply({ message: "Limits temporarily unavailable" }, false) : reply(limits),
      );
      return Promise.resolve(
        catalogUnavailable ? reply({ message: "Catalog temporarily unavailable" }, false) : reply(catalog),
      );
    }
    return new Promise((resolve, reject) => requests.push({ path, init, resolve, reject }));
  };
  await import(`${pathToFileURL(join(moduleDirectory, "app.js"))}?test=${++instance}`);
  await settle();
  const element = (id) => elements.get(`#${id}`);
  element("workflow-editor").value = '{"version":1,"steps":[]}';
  element("layer-names").value = "source";
  return { element, requests, metadataRequests,
    click: () => element("review-button").dispatch("click"),
    preflight: () => element("preflight-button").dispatch("click") };
}
function reply(payload, ok = true) { return { ok, status: ok ? 200 : 503, text: async () => JSON.stringify(payload) }; }
async function settle() { for (let i = 0; i < 8; i += 1) await Promise.resolve(); }
function canonicalReports(digest = "current-plan", { required = ["source"], unused = [] } = {}) {
  const common = { schema_version: 1, workflow_version: 1, workflow_digest: "current-workflow",
    operator_catalog_version: 1, operator_catalog_digest: "current-catalog", plan_digest: digest };
  const plan = { ...common, declared_external_layers: [...required, ...unused],
    required_external_layers: required, unused_external_layers: unused, produced_layers: [],
    terminal_layers: [], step_count: 0, steps: [] };
  const contract = { ...common, contract_digest: "current-contract", layers: required.map((name) => ({
    name, required: true, unused: false, use_count: 0, uses: [],
  })), remaining_checks: [] };
  const graph = { ...common, graph_digest: "current-graph", nodes: [], edges: [] };
  const explain = { ...common, graph_digest: graph.graph_digest,
    explanation_digest: "current-explanation", steps: [] };
  return { plan, contract, graph, explain };
}
function resolveReports(requests, digest = "current-plan", options = {}) {
  const reports = canonicalReports(digest, options);
  for (const request of requests.splice(0)) {
    const endpoint = request.path.split("/").at(-1);
    assert.ok(Object.hasOwn(reports, endpoint), `Unexpected report request: ${request.path}`);
    request.resolve(reply(reports[endpoint]));
  }
}
async function succeed(context, options = {}) {
  const done = context.click();
  context.requests.shift().resolve(reply({ valid: true }));
  await settle();
  assert.equal(context.requests.length, 4);
  resolveReports(context.requests, "current-plan", options);
  await done;
  assert.equal(context.element("review-state").textContent, "Reviewed");
  assert.match(context.element("evidence-content").textContent, /current-plan/);
}
function assertEmpty(context) {
  for (const id of ["overview", "contract", "graph", "explain", "evidence"]) {
    assert.equal(context.element(`${id}-content`).textContent, "Run Review to generate current evidence.");
  }
}

test("retry clears successful evidence immediately and keeps it cleared on server failure", async () => {
  const context = await setup();
  await succeed(context);
  const retry = context.click();
  assertEmpty(context);
  assert.equal(context.element("review-button").disabled, true);
  context.requests.shift().resolve(reply({ message: "Temporarily unavailable" }, false));
  await retry;
  assertEmpty(context);
  assert.equal(context.element("review-state").textContent, "Review failed");
  assert.equal(context.element("review-button").disabled, false);
});

test("invalid JSON retry clears old reports without making an HTTP request", async () => {
  const context = await setup();
  await succeed(context);
  context.element("workflow-editor").value = "{";
  await context.click();
  assertEmpty(context);
  assert.equal(context.requests.length, 0);
  assert.equal(context.element("review-state").textContent, "Review failed");
});

test("input invalidation releases controls and stale validation does not request reports", async () => {
  const context = await setup();
  const pending = context.click();
  const validation = context.requests.shift();
  context.element("workflow-editor").dispatch("input");
  assertEmpty(context);
  assert.equal(context.element("review-button").disabled, false);
  validation.resolve(reply({ valid: true }));
  await pending;
  assert.equal(context.requests.length, 0);
  assert.equal(context.element("review-state").textContent, "Not reviewed");
  assert.equal(context.element("request-status").textContent,
    "Inputs changed. Review again for current evidence.");
});

test("stale report completion cannot restore panels or release a newer review's controls", async () => {
  const context = await setup();
  const oldReview = context.click();
  context.requests.shift().resolve(reply({ valid: true }));
  await settle();
  const oldReports = context.requests.splice(0);
  context.element("layer-names").dispatch("input");
  const currentReview = context.click();
  const currentValidation = context.requests.shift();
  resolveReports(oldReports, "stale-plan");
  await oldReview;
  assertEmpty(context);
  assert.equal(context.element("review-button").disabled, true);
  assert.equal(context.element("review-state").textContent, "Reviewing");
  currentValidation.resolve(reply({ valid: true }));
  await settle();
  resolveReports(context.requests);
  await currentReview;
  assert.equal(context.element("review-state").textContent, "Reviewed");
  assert.doesNotMatch(context.element("evidence-content").textContent, /stale-plan/);
});

test("mismatched canonical report chain leaves no successful evidence", async () => {
  const context = await setup();
  await succeed(context);
  const retry = context.click();
  context.requests.shift().resolve(reply({ valid: true }));
  await settle();
  context.requests.shift().resolve(reply({ plan_digest: "mismatch" }));
  resolveReports(context.requests);
  await retry;
  assertEmpty(context);
  assert.equal(context.element("review-state").textContent, "Review failed");
  assert.match(context.element("request-status").textContent, /canonical evidence chain/);
});

for (const input of ["workflow-editor", "layer-names"]) {
  test(`${input} edit clears stale success and failure request statuses`, async () => {
    const context = await setup();
    await succeed(context);
    context.element(input).dispatch("input");
    assertEmpty(context);
    assert.equal(context.element("request-status").textContent,
      "Inputs changed. Review again for current evidence.");
    assert.equal(context.element("review-state").textContent, "Not reviewed");
    const failed = context.click();
    context.requests.shift().resolve(reply({ message: "Temporarily unavailable" }, false));
    await failed;
    assert.equal(context.element("request-status").classList.contains("is-error"), true);
    context.element(input).dispatch("input");
    assertEmpty(context);
    assert.equal(context.element("request-status").textContent,
      "Inputs changed. Review again for current evidence.");
    assert.equal(context.element("request-status").classList.contains("is-error"), false);
    assert.equal(context.element("review-state").textContent, "Not reviewed");
    assert.equal(context.element("review-button").disabled, false);
  });
}

function selectDraft(context) {
  context.element("builder-operator").value = "synthetic_operator";
  context.element("builder-operator").dispatch("change");
  const fields = context.element("step-builder-fields");
  fields.querySelector("[data-step-input]").value = "source";
  fields.querySelector("[data-step-parameter]").value = "3";
  fields.querySelector("[data-step-output]").value = "result";
  return fields;
}
function insert(context) { return context.element("add-step-button").dispatch("click"); }

test("insertion during validation invalidates its ownership and appends exactly one draft", async () => {
  const context = await setup();
  selectDraft(context);
  const pending = context.click();
  const validation = context.requests.shift();
  insert(context);
  const workflow = JSON.parse(context.element("workflow-editor").value);
  assert.deepEqual(workflow.steps, [{ operation: "synthetic_operator", inputs: { source: "source" },
    parameters: { amount: 3 }, output: "result" }]);
  assertEmpty(context);
  assert.equal(context.element("review-state").textContent, "Not reviewed");
  assert.equal(context.element("review-button").disabled, false);
  validation.resolve(reply({ valid: true }));
  await pending;
  assert.equal(context.requests.length, 0);
  assertEmpty(context);
  await succeed(context);
});

test("insertion during reports cannot let stale reports unlock a newer request", async () => {
  const context = await setup();
  selectDraft(context);
  const old = context.click();
  context.requests.shift().resolve(reply({ valid: true }));
  await settle();
  const oldReports = context.requests.splice(0);
  insert(context);
  const current = context.click();
  const validation = context.requests.shift();
  resolveReports(oldReports, "stale-plan");
  await old;
  assertEmpty(context);
  assert.equal(context.element("review-button").disabled, true);
  assert.equal(context.element("review-state").textContent, "Reviewing");
  validation.resolve(reply({ valid: true }));
  await settle();
  resolveReports(context.requests);
  await current;
  assert.equal(context.element("review-state").textContent, "Reviewed");
  assert.doesNotMatch(context.element("evidence-content").textContent, /stale-plan/);
  context.element("workflow-editor").dispatch("input");
  assertEmpty(context);
  await succeed(context);
});

test("invalid parameter syntax and invalid workflow preserve JSON and reviewed evidence", async () => {
  const context = await setup();
  await succeed(context);
  const fields = selectDraft(context);
  const before = context.element("workflow-editor").value;
  fields.querySelector("[data-step-parameter]").value = "not JSON";
  insert(context);
  assert.equal(context.element("workflow-editor").value, before);
  assert.match(context.element("builder-status").textContent, /valid JSON/);
  assert.equal(context.element("review-state").textContent, "Reviewed");
  context.element("workflow-editor").value = "{";
  context.element("workflow-editor").dispatch("input");
  insert(context);
  assert.equal(context.element("workflow-editor").value, "{");
  assertEmpty(context);
  assert.equal(context.requests.length, 0);
});

test("builder displays unresolved complete catalog hints and updates suggestions without dropping fields", async () => {
  const context = await setup();
  const fields = selectDraft(context);
  for (const hint of ["Unresolved", "Point", "CRS contract", "Required field declarations",
    "Written field declarations", "Unresolved note", "Core default: false", "Schema:"]) {
    assert.ok(fields.textContent.includes(hint), hint);
  }
  context.element("workflow-editor").value = '{"version":1,"steps":[{"output":"produced"}]}';
  context.element("layer-names").value = "source\nextra";
  context.element("layer-names").dispatch("input");
  assert.deepEqual(fields.querySelector("#builder-layer-suggestions").children.map((x) => x.value),
    ["source", "extra", "produced"]);
  assert.equal(fields.querySelector("[data-step-parameter]").value, "3");
});


for (const token of ["1e400", "9007199254740993"]) {
  test(`insertion preserves raw workflow and prior evidence on nested numeric limit ${token}`, async () => {
    const context = await setup();
    // The controlled service supplies prior evidence; this test isolates insertion ownership.
    const original = `{ "version":1, "steps":[{"parameters":{"nested":[${token}]}}] }`;
    context.element("workflow-editor").value = original;
    await succeed(context);
    const evidence = context.element("evidence-content").textContent;
    selectDraft(context);
    insert(context);
    assert.equal(context.element("workflow-editor").value, original);
    assert.equal(context.element("evidence-content").textContent, evidence);
    assert.equal(context.element("review-state").textContent, "Reviewed");
    assert.match(context.element("builder-status").textContent, /browser numeric limits/);
    assert.equal(context.requests.length, 0);
  });

  test(`insertion rejects nested parameter numeric limit ${token} without mutation`, async () => {
    const context = await setup();
    await succeed(context);
    const fields = selectDraft(context);
    const original = context.element("workflow-editor").value;
    const evidence = context.element("evidence-content").textContent;
    fields.querySelector("[data-step-parameter]").value = `{"nested":[${token}]}`;
    insert(context);
    assert.equal(context.element("workflow-editor").value, original);
    assert.equal(context.element("evidence-content").textContent, evidence);
    assert.equal(context.element("review-state").textContent, "Reviewed");
    assert.match(context.element("builder-status").textContent, /browser numeric limits/);
    assert.equal(context.requests.length, 0);
  });
}


test("catalog failure replaces loading placeholder, disables drafting, and permits manual review", async () => {
  const context = await setup({ catalogUnavailable: true });
  const select = context.element("builder-operator");
  assert.equal(select.disabled, true);
  assert.equal(select.textContent, "Catalog unavailable");
  assert.equal(select.children.length, 1);
  assert.equal(select.firstChild.value, "");
  assert.equal(context.element("add-step-button").disabled, true);
  assert.match(context.element("builder-status").textContent, /Catalog unavailable/);
  assert.equal(context.element("review-button").disabled, false);
  await succeed(context);
  assert.equal(select.disabled, true);
  assert.equal(select.textContent, "Catalog unavailable");
});

test("review snapshots exact input for all requests and Evidence keeps original response text", async () => {
  const context = await setup();
  const rawWorkflow = '{"version":1.0,"steps":[],"values":[8.0,-0.0,9007199254740993,1e400]}';
  context.element("workflow-editor").value = rawWorkflow;
  context.element("layer-names").value = 'quote"\\layer';
  const done = context.click();
  const validation = context.requests.shift();
  const body = `{"workflow":${rawWorkflow},"layer_names":["quote\\\"\\\\layer"]}`;
  assert.equal(validation.init.body, body);
  const validationRaw = ' {"valid":true,"workflow_version":1.0}\n';
  validation.resolve({ ok: true, text: async () => validationRaw });
  // Programmatic changes without input events must not mix request snapshots.
  context.element("workflow-editor").value = '{}';
  context.element("layer-names").value = 'different';
  await settle();
  const raw = ' {"workflow_digest":"workflow","plan_digest":"exact","contract_digest":"contract","graph_digest":"graph","required_external_layers":[],"unused_external_layers":[],"steps":[{"parameters":[{"name":"nested","value":{"array":[9007199254740993,-0.0,8.0]},"source":"supplied"}]}],"html":"<img src=x onerror=alert(1)>"}\n';
  for (const request of context.requests.splice(0)) {
    assert.equal(request.init.body, body);
    request.resolve({ ok: true, text: async () => raw });
  }
  await done;
  assert.equal(context.element("review-state").textContent, "Reviewed");
  const blocks = context.element("evidence-content").children.filter((node) => node.className === "raw-block");
  assert.equal(blocks.length, 5);
  assert.equal(blocks[0].textContent, validationRaw);
  for (const block of blocks.slice(1)) {
    assert.equal(block.textContent, raw);
    assert.equal(block.children.length, 0); // JSON HTML remains text, not DOM.
  }
  assert.doesNotMatch(context.element("explain-content").textContent, /9007199254740992/);
  assert.match(context.element("explain-content").textContent, /See exact JSON in Evidence/);
  for (const id of ["overview", "contract", "graph", "explain"]) {
    assert.match(context.element(`${id}-content`).textContent, /numeric spelling may be normalized/);
  }
});

test("Evidence never fabricates exact JSON when original response text is unavailable", async () => {
  const context = await setup();
  const { renderReports } = await import(pathToFileURL(join(moduleDirectory, "render.js")));
  const containers = Object.fromEntries(["overview", "contract", "graph", "explain", "evidence"]
    .map((name) => [name, context.element(`${name}-content`)]));
  renderReports(containers, { validation: {}, plan: {}, contract: {}, graph: {}, explain: {} });
  const blocks = containers.evidence.children.filter((node) => node.className === "raw-block");
  assert.equal(blocks.length, 5);
  for (const block of blocks) assert.equal(block.textContent, "Original response unavailable.");
});

// These lifecycle checks use the real transport and renderers. The fake service
// controls completion order so obsolete success, catch, and finally paths run.
const collectionText = '{"type":"FeatureCollection","features":[]}';
function binding(context, name = "source") {
  const control = context.element("preflight-bindings").querySelectorAll("[data-layer-name]")
    .find((node) => node.dataset.layerName === name);
  assert.ok(control, `Missing required binding: ${name}`);
  return control;
}
function typeLayer(context, raw = collectionText, name = "source") {
  const control = binding(context, name);
  control.value = raw;
  control.dispatch("input");
  return control;
}
function preflightReport(overrides = {}) {
  return { schema_version: 1, workflow_version: 1, workflow_digest: "current-workflow",
    operator_catalog_version: 1, operator_catalog_digest: "current-catalog",
    plan_digest: "current-plan", contract_digest: "current-contract", valid: true,
    layer_count: 1, checked_layer_count: 1, error_count: 0, warning_count: 0,
    layers: [{ name: "source", required: true, unused: false, status: "passed",
      collection_digest: "current-collection", feature_count: 2, declared_crs: "EPSG:4326",
      geometry_counts: { Point: 2 }, error_count: 0, warning_count: 0 }],
    findings: [], remaining_checks: ["Execution-time topology remains unchecked."],
    preflight_digest: "current-preflight", ...overrides };
}
function takePreflight(context) {
  assert.equal(context.requests.length, 1);
  const request = context.requests.shift();
  assert.equal(request.path, "/api/v1/workflows/preflight");
  assert.equal(request.init.method, "POST");
  return request;
}
function assertNoPreflight(context) {
  assert.equal(context.element("preflight-content").textContent,
    "No current Preflight evidence. Run Preflight after Review.");
}
async function succeedPreflight(context, overrides = {}) {
  const pending = context.preflight();
  takePreflight(context).resolve(reply(preflightReport(overrides)));
  await pending;
  assert.match(context.element("preflight-content").textContent, /current-preflight/);
}
function preflightSnapshot(context) {
  return { content: context.element("preflight-content").textContent,
    status: context.element("preflight-status").textContent,
    error: context.element("preflight-status").classList.contains("is-error"),
    disabled: context.element("preflight-button").disabled,
    review: context.element("review-state").textContent,
    reviewDisabled: context.element("review-button").disabled };
}
function finishObsolete(request, outcome) {
  if (outcome === "success") request.resolve(reply(preflightReport({ preflight_digest: "obsolete-preflight" })));
  else request.reject(new Error("Obsolete network failure must not replace current status."));
}

test("Preflight metadata is a separate read and Review creates only canonical required slots", async () => {
  const context = await setup();
  assert.equal(context.element("preflight-button").disabled, true);
  assertNoPreflight(context);
  assert.equal(context.requests.length, 0);
  const limitsRequest = context.metadataRequests.filter(({ path }) => path === "/api/v1/limits");
  assert.equal(limitsRequest.length, 1);
  assert.equal(limitsRequest[0].init.method, "GET");
  assert.equal(limitsRequest[0].init.body, undefined);
  assert.match(context.element("preflight-limits").textContent, /max_request_bytes/);
  await succeed(context, { required: ["source", "boundary"], unused: ["unused"] });
  assert.deepEqual(context.element("preflight-bindings").querySelectorAll("[data-layer-name]")
    .map((node) => node.dataset.layerName), ["source", "boundary"]);
  assert.match(context.element("preflight-bindings").textContent, /unused/);
  assert.equal(context.element("preflight-button").disabled, true);
  await context.preflight();
  assert.equal(context.requests.length, 0);
  await succeed(context, { required: ["source", "boundary"] });
  assert.equal(context.element("preflight-button").disabled, false);
});

test("unavailable inline limits do not block independent catalog loading or manual Review", async () => {
  const context = await setup({ limitsUnavailable: true });
  assert.equal(context.element("builder-operator").disabled, false);
  assert.match(context.element("preflight-limits").textContent, /unavailable/i);
  await succeed(context);
  assert.equal(context.element("preflight-button").disabled, false);
});

test("layer typing sends nothing, keeps Review, and never replaces the active textarea", async () => {
  const context = await setup();
  await succeed(context);
  const evidence = context.element("evidence-content").textContent;
  const control = binding(context);
  const metadataCount = context.metadataRequests.length;
  for (const raw of ["{", '{"type":', collectionText]) {
    typeLayer(context, raw);
    assert.equal(binding(context), control);
    assert.equal(context.element("evidence-content").textContent, evidence);
    assert.equal(context.element("review-state").textContent, "Reviewed");
    assert.equal(context.requests.length, 0);
    assert.equal(context.metadataRequests.length, metadataCount);
  }
  await succeedPreflight(context);
  typeLayer(context, '{"type":"FeatureCollection","features":[],"edited":true}');
  assertNoPreflight(context);
  assert.equal(binding(context), control);
  assert.equal(context.element("evidence-content").textContent, evidence);
  assert.equal(context.element("review-state").textContent, "Reviewed");
  assert.equal(context.element("preflight-button").disabled, false);
  assert.equal(context.requests.length, 0);
});

test("explicit Preflight preserves exact reviewed workflow and per-layer JSON snapshots", async () => {
  const context = await setup();
  const workflow = '{"version":1.0,"steps":[],"values":[8.0,-0.0,9007199254740993,1e400]}';
  const name = 'quote"\\layer';
  const rawLayer = ' {"type":"FeatureCollection","features":[],"numbers":[8.0,-0.0,9007199254740993,1e400]}\n';
  context.element("workflow-editor").value = workflow;
  await succeed(context, { required: [name] });
  typeLayer(context, rawLayer, name);
  // DOM edits without input events cannot change a reviewed workflow snapshot.
  context.element("workflow-editor").value = '{"different":true}';
  const pending = context.preflight();
  const request = takePreflight(context);
  assert.equal(request.init.body, `{"workflow":${workflow},"layers":{${JSON.stringify(name)}:${rawLayer}}}`);
  assert.equal(request.init.credentials, "same-origin");
  binding(context, name).value = '{"changedWithoutInputEvent":true}';
  const rawReport = ` ${JSON.stringify(preflightReport())}\n`;
  request.resolve({ ok: true, text: async () => rawReport });
  await pending;
  const blocks = context.element("preflight-content").querySelectorAll("pre");
  assert.equal(blocks.at(-1).textContent, rawReport);
  assert.equal(blocks.at(-1).children.length, 0);
  const layerCard = context.element("preflight-content").children.find((node) => node.tagName === "ARTICLE");
  assert.match(layerCard.textContent, /Geometry counts: \{"Point":2\}/);
  assert.match(context.element("preflight-content").textContent, /Execution-time topology remains unchecked/);
  assert.equal(context.element("review-state").textContent, "Reviewed");
});

test("invalid layer JSON clears prior Preflight without transmitting or invalidating Review", async () => {
  const context = await setup();
  await succeed(context);
  typeLayer(context);
  await succeedPreflight(context);
  typeLayer(context, "{");
  await context.preflight();
  assertNoPreflight(context);
  assert.equal(context.requests.length, 0);
  assert.match(context.element("preflight-status").textContent, /valid JSON/);
  assert.equal(context.element("preflight-status").classList.contains("is-error"), true);
  assert.equal(context.element("review-state").textContent, "Reviewed");
  assert.equal(context.element("preflight-button").disabled, false);
});

test("empty required bindings are omitted rather than replaced with fabricated data", async () => {
  const context = await setup();
  await succeed(context, { required: ["source", "missing"] });
  typeLayer(context);
  typeLayer(context, " \n", "missing");
  const pending = context.preflight();
  const request = takePreflight(context);
  assert.deepEqual(Object.keys(JSON.parse(request.init.body).layers), ["source"]);
  request.resolve(reply({ message: "Missing external layer: missing" }, false));
  await pending;
  assertNoPreflight(context);
  assert.match(context.element("preflight-status").textContent, /Missing external layer/);
});

test("HTTP failure clears evidence while HTTP 200 canonical FAIL renders authoritative findings", async () => {
  const context = await setup();
  await succeed(context);
  typeLayer(context);
  await succeedPreflight(context);
  const failedRequest = context.preflight();
  assertNoPreflight(context);
  takePreflight(context).resolve(reply({ diagnostic: { message: "Request limit exceeded" } }, false));
  await failedRequest;
  assertNoPreflight(context);
  assert.match(context.element("preflight-status").textContent, /Request limit exceeded/);
  assert.equal(context.element("preflight-status").classList.contains("is-error"), true);
  const failedReport = preflightReport({ valid: false, error_count: 1,
    findings: [{ severity: "error", code: "synthetic_geometry_failure", layer: "source",
      message: "Canonical geometry check failed <img src=x onerror=alert(1)>.", occurrence_count: 1 }] });
  const pending = context.preflight();
  takePreflight(context).resolve(reply(failedReport));
  await pending;
  const content = context.element("preflight-content");
  assert.equal(content.children[0].textContent, "FAIL");
  assert.match(content.textContent, /synthetic_geometry_failure/);
  assert.match(content.textContent, /current-preflight/);
  assert.equal(content.querySelectorAll("img").length, 0);
  assert.equal(context.element("preflight-status").textContent, "Canonical Preflight complete: FAIL.");
  assert.equal(context.element("review-state").textContent, "Reviewed");
  assert.equal(context.element("preflight-button").disabled, false);
});

for (const digest of ["workflow_digest", "plan_digest", "contract_digest"]) {
  test(`Preflight rejects a mismatched ${digest} rather than displaying canonical evidence`, async () => {
    const context = await setup();
    await succeed(context);
    typeLayer(context);
    const pending = context.preflight();
    takePreflight(context).resolve(reply(preflightReport({ [digest]: "mismatched-evidence" })));
    await pending;
    assertNoPreflight(context);
    assert.match(context.element("preflight-status").textContent, /canonical Review evidence chain/);
    assert.equal(context.element("preflight-status").classList.contains("is-error"), true);
    assert.equal(context.element("review-state").textContent, "Reviewed");
    assert.equal(context.element("preflight-button").disabled, false);
  });
}

for (const outcome of ["success", "error"]) {
  for (const input of ["data", "workflow-editor", "layer-names"]) {
    test(`late Preflight ${outcome} and finally cannot undo ${input} invalidation`, async () => {
      const context = await setup();
      await succeed(context);
      typeLayer(context);
      const pending = context.preflight();
      const obsolete = takePreflight(context);
      assert.equal(context.element("preflight-button").disabled, true);
      if (input === "data") typeLayer(context, `${collectionText}\n`);
      else context.element(input).dispatch("input");
      assertNoPreflight(context);
      if (input === "data") {
        assert.equal(context.element("review-state").textContent, "Reviewed");
        assert.equal(context.element("preflight-button").disabled, false);
      } else {
        assertEmpty(context);
        assert.equal(context.element("review-state").textContent, "Not reviewed");
        assert.equal(context.element("preflight-button").disabled, true);
      }
      const current = preflightSnapshot(context);
      finishObsolete(obsolete, outcome);
      await pending;
      assert.deepEqual(preflightSnapshot(context), current);
      assert.equal(context.requests.length, 0);
    });
  }

  for (const invalidateData of [false, true]) {
    test(`obsolete Preflight ${outcome} cannot unlock a newer ${invalidateData ? "edited" : "repeated"} Preflight`, async () => {
      const context = await setup();
      await succeed(context);
      typeLayer(context);
      const old = context.preflight();
      const obsolete = takePreflight(context);
      if (invalidateData) typeLayer(context, `${collectionText}\n`);
      const current = context.preflight();
      const request = takePreflight(context);
      assertNoPreflight(context);
      assert.equal(context.element("preflight-button").disabled, true);
      const before = preflightSnapshot(context);
      finishObsolete(obsolete, outcome);
      await old;
      assert.deepEqual(preflightSnapshot(context), before);
      request.resolve(reply(preflightReport()));
      await current;
      assert.equal(context.element("preflight-button").disabled, false);
      assert.match(context.element("preflight-content").textContent, /current-preflight/);
      assert.doesNotMatch(context.element("preflight-content").textContent, /obsolete-preflight/);
    });
  }

  test(`replacement Review owns its controls when obsolete Preflight ${outcome} finishes`, async () => {
    const context = await setup();
    await succeed(context);
    typeLayer(context);
    const old = context.preflight();
    const obsolete = takePreflight(context);
    const review = context.click();
    const validation = context.requests.shift();
    assertEmpty(context);
    assertNoPreflight(context);
    assert.equal(context.element("review-button").disabled, true);
    assert.equal(context.element("preflight-button").disabled, true);
    const before = preflightSnapshot(context);
    finishObsolete(obsolete, outcome);
    await old;
    assert.deepEqual(preflightSnapshot(context), before);
    validation.resolve(reply({ valid: true }));
    await settle();
    resolveReports(context.requests);
    await review;
    assert.equal(context.element("review-state").textContent, "Reviewed");
    assert.equal(context.element("review-button").disabled, false);
    assert.equal(context.element("preflight-button").disabled, false);
    assertNoPreflight(context);
    assert.equal(binding(context).value, collectionText);
  });
}

test("Review reconciles exact layer names while preserving matched and unbound drafts", async () => {
  const context = await setup();
  await succeed(context, { required: ["source", "retained"] });
  const sourceDraft = `${collectionText}\n`;
  const orphanDraft = ' {"type":"FeatureCollection","features":[],"label":"keep exact"} ';
  typeLayer(context, sourceDraft);
  typeLayer(context, orphanDraft, "retained");
  context.element("layer-names").value = "source\nnew";
  context.element("layer-names").dispatch("input");
  await succeed(context, { required: ["source", "new"] });
  assert.equal(binding(context).value, sourceDraft);
  assert.equal(binding(context, "new").value, "");
  const orphans = context.element("preflight-bindings").querySelectorAll("textarea")
    .filter((node) => node.readOnly);
  assert.equal(orphans.length, 1);
  assert.equal(orphans[0].value, orphanDraft);
  assert.match(context.element("preflight-bindings").textContent, /Retained unbound draft: retained/);
  typeLayer(context, collectionText, "new");
  const pending = context.preflight();
  const request = takePreflight(context);
  assert.deepEqual(Object.keys(JSON.parse(request.init.body).layers), ["source", "new"]);
  assert.equal(request.init.body.includes("keep exact"), false);
  request.resolve(reply(preflightReport()));
  await pending;
  context.element("workflow-editor").dispatch("input");
  await succeed(context, { required: ["retained", "Source"] });
  assert.equal(binding(context, "retained").value, orphanDraft);
  assert.equal(binding(context, "Source").value, "");
  assert.equal(binding(context, "retained").readOnly, false);
  assert.equal(context.requests.length, 0);
});

for (const outcome of ["success", "error"]) {
  test(`Preflight from a replaced Review cannot ${outcome === "success" ? "publish" : "report an error"} or unlock current Preflight`, async () => {
    const context = await setup();
    await succeed(context);
    typeLayer(context);
    const old = context.preflight();
    const obsolete = takePreflight(context);
    await succeed(context);
    const current = context.preflight();
    const request = takePreflight(context);
    const before = preflightSnapshot(context);
    assert.equal(before.disabled, true);
    finishObsolete(obsolete, outcome);
    await old;
    assert.deepEqual(preflightSnapshot(context), before);
    request.resolve(reply(preflightReport()));
    await current;
    assert.equal(context.element("preflight-button").disabled, false);
    assert.match(context.element("preflight-content").textContent, /current-preflight/);
    assert.doesNotMatch(context.element("preflight-content").textContent, /obsolete-preflight/);
  });
}

test("failed replacement Review preserves raw drafts without leaving stale Preflight enabled", async () => {
  const context = await setup();
  await succeed(context);
  const raw = ` ${collectionText}\n`;
  typeLayer(context, raw);
  await succeedPreflight(context);
  const review = context.click();
  context.requests.shift().resolve(reply({ message: "Validation unavailable" }, false));
  await review;
  assertEmpty(context);
  assertNoPreflight(context);
  assert.equal(context.element("preflight-button").disabled, true);
  const retained = context.element("preflight-bindings").querySelectorAll("textarea");
  assert.equal(retained.length, 1);
  assert.equal(retained[0].readOnly, true);
  assert.equal(retained[0].value, raw);
  await succeed(context);
  assert.equal(binding(context).value, raw);
  assert.equal(binding(context).readOnly, false);
});

test("prototype-like layer names remain independent draft keys across Review and Preflight", async () => {
  const context = await setup();
  const names = ["__proto__", "constructor", "toString"];
  await succeed(context, { required: names });
  for (const [index, name] of names.entries()) {
    typeLayer(context, `{"type":"FeatureCollection","features":[],"marker":${index}}`, name);
  }
  await succeed(context, { required: names });
  const pending = context.preflight();
  const request = takePreflight(context);
  const layers = JSON.parse(request.init.body).layers;
  assert.deepEqual(Object.keys(layers), names);
  for (const [index, name] of names.entries()) assert.equal(layers[name].marker, index);
  request.resolve(reply(preflightReport()));
  await pending;
  assert.equal(context.element("preflight-button").disabled, false);
});
