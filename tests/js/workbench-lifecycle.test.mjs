import assert from "node:assert/strict";
import test, { after } from "node:test";
import { copyFileSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

// A temporary package marks exact, unmodified asset copies as ES modules on Node 18+.
const moduleDirectory = mkdtempSync(join(tmpdir(), "starshine-workbench-test-"));
writeFileSync(join(moduleDirectory, "package.json"), '{"type":"module"}');
for (const name of ["app.js", "api.js", "render.js", "editor.js", "render_editor.js"]) {
  copyFileSync(new URL(`../../src/starshine_server/static/${name}`, import.meta.url), join(moduleDirectory, name));
}
after(() => rmSync(moduleDirectory, { recursive: true, force: true }));

// Exercise the shipped modules with an in-memory DOM and controlled HTTP replies.
// This checks request ownership and rendered evidence, not browser layout or CSP.
class Element {
  children = [];
  dataset = {};
  attributes = {};
  listeners = new Map();
  disabled = false;
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
      : Object.hasOwn(element.dataset, selector.slice(6, -1).replace(/-([a-z])/g, (_, c) => c.toUpperCase()));
    return this.children.flatMap((child) => [ ...(matches(child) ? [child] : []), ...child.querySelectorAll(selector)]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  dispatch(name) { return this.listeners.get(name)?.(); }
}

let instance = 0;
const catalog = { operators: [{ name: "synthetic_operator", summary: "Synthetic operation",
  inputs: [{ name: "source", contract: { geometry_types: ["Point"], crs: { mode: "parameter" },
    required_fields: [{ parameter: "field" }], written_fields: [{ name: "result" }], notes: ["Unresolved note"] } }],
  parameters: [{ name: "amount", required: true, schema: { type: "number" } },
    { name: "optional", default: false, schema: { type: "boolean" } }],
}] };
async function setup({ catalogUnavailable = false } = {}) {
  const elements = new Map();
  globalThis.document = {
    querySelector(selector) {
      if (!elements.has(selector)) elements.set(selector, new Element());
      return elements.get(selector);
    },
    querySelectorAll() { return []; },
    createElement() { return new Element(); },
  };
  document.querySelector("#builder-operator").disabled = true;
  const loadingOption = document.createElement("option");
  loadingOption.textContent = "Loading canonical catalog…";
  document.querySelector("#builder-operator").appendChild(loadingOption);
  document.querySelector("#add-step-button").disabled = true;
  const requests = [];
  globalThis.fetch = (path, init) => {
    if (path === "/healthz") return Promise.resolve(reply({ core_version: "test" }));
    if (path === "/api/v1/operators") return Promise.resolve(
      catalogUnavailable ? reply({ message: "Catalog temporarily unavailable" }, false) : reply(catalog),
    );
    return new Promise((resolve, reject) => requests.push({ path, init, resolve, reject }));
  };
  await import(`${pathToFileURL(join(moduleDirectory, "app.js"))}?test=${++instance}`);
  await settle();
  const element = (id) => elements.get(`#${id}`);
  element("workflow-editor").value = '{"version":1,"steps":[]}';
  element("layer-names").value = "source";
  return { element, requests, click: () => element("review-button").dispatch("click") };
}
function reply(payload, ok = true) { return { ok, status: ok ? 200 : 503, text: async () => JSON.stringify(payload) }; }
async function settle() { for (let i = 0; i < 8; i += 1) await Promise.resolve(); }
function resolveReports(requests, digest = "current-plan") {
  for (const request of requests.splice(0)) {
    const payload = { plan_digest: digest, graph_digest: "current-graph", valid: true };
    request.resolve(reply(payload));
  }
}
async function succeed(context) {
  const done = context.click();
  context.requests.shift().resolve(reply({ valid: true }));
  await settle();
  assert.equal(context.requests.length, 4);
  resolveReports(context.requests);
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
  const raw = ' {"plan_digest":"exact","graph_digest":"graph","steps":[{"parameters":[{"name":"nested","value":{"array":[9007199254740993,-0.0,8.0]},"source":"supplied"}]}],"html":"<img src=x onerror=alert(1)>"}\n';
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
