import assert from "node:assert/strict";
import test, { after } from "node:test";
import { copyFileSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

// A temporary package marks exact, unmodified asset copies as ES modules on Node 18+.
const moduleDirectory = mkdtempSync(join(tmpdir(), "starshine-workbench-test-"));
writeFileSync(join(moduleDirectory, "package.json"), '{"type":"module"}');
for (const name of ["app.js", "api.js", "render.js"]) {
  copyFileSync(new URL(`../../src/starshine_server/static/${name}`, import.meta.url), join(moduleDirectory, name));
}
after(() => rmSync(moduleDirectory, { recursive: true, force: true }));

// Exercise the shipped modules with an in-memory DOM and controlled HTTP replies.
// This checks request ownership and rendered evidence, not browser layout or CSP.
class Element {
  children = [];
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
  dispatch(name) { return this.listeners.get(name)?.(); }
}

let instance = 0;
async function setup() {
  const elements = new Map();
  globalThis.document = {
    querySelector(selector) {
      if (!elements.has(selector)) elements.set(selector, new Element());
      return elements.get(selector);
    },
    querySelectorAll() { return []; },
    createElement() { return new Element(); },
  };
  const requests = [];
  globalThis.fetch = (path) => {
    if (path === "/healthz") return Promise.resolve(reply({ core_version: "test" }));
    if (path === "/api/v1/operators") return Promise.resolve(reply({ operators: [] }));
    return new Promise((resolve, reject) => requests.push({ path, resolve, reject }));
  };
  await import(`${pathToFileURL(join(moduleDirectory, "app.js"))}?test=${++instance}`);
  await settle();
  const element = (id) => elements.get(`#${id}`);
  element("workflow-editor").value = '{"version":1,"steps":[]}';
  element("layer-names").value = "source";
  return { element, requests, click: () => element("review-button").dispatch("click") };
}
function reply(payload, ok = true) { return { ok, status: ok ? 200 : 503, json: async () => payload }; }
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
