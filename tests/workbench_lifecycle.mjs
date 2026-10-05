// Run with: node --experimental-vm-modules --test tests/workbench_lifecycle.mjs
// Exercise the actual app, transport, and pure helpers; only DOM presentation and HTTP are doubled.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { setImmediate as tick } from "node:timers/promises";
import { test } from "node:test";
import { createContext, SourceTextModule, SyntheticModule } from "node:vm";

const staticRoot = new URL("../src/starshine_server/static/", import.meta.url);
const workflow = { version: 1, steps: [] };
const policy = { mode: "isolated_subprocess", timeout_seconds: 10 };
const preflight = {
  valid: true, plan_digest: "plan", contract_digest: "contract", preflight_digest: "preflight",
};
const fixtures = {
  "/healthz": { core_version: "test" },
  "/api/v1/operators": { operators: [] },
  "/api/v1/limits": { inline_execution: policy, inline_preflight: {} },
  "/api/v1/workflows/validate": { valid: true, workflow_version: 1 },
  "/api/v1/workflows/plan": {
    plan_digest: "plan", required_external_layers: ["source"], terminal_layers: ["result"],
  },
  "/api/v1/workflows/contract": { plan_digest: "plan", contract_digest: "contract" },
  "/api/v1/workflows/graph": { plan_digest: "plan", graph_digest: "graph" },
  "/api/v1/workflows/explain": { plan_digest: "plan", graph_digest: "graph" },
  "/api/v1/workflows/preflight": preflight,
  "/api/v1/workflows/execute": {
    status: "succeeded", output_layer: "result", preflight, execution_policy: policy,
    result: { type: "FeatureCollection", features: [] }, manifest: {},
  },
};
const pathFor = (name) => `/api/v1/workflows/${name}`;
const reply = (payload) => ({ ok: true, status: 200, json: async () => structuredClone(payload) });

async function harness() {
  const controls = new Map();
  const calls = [];
  const held = new Map();
  const rendered = [];
  function control(selector) {
    if (!controls.has(selector)) {
      controls.set(selector, {
        value: "", textContent: "", disabled: false, dataset: {}, handlers: {},
        addEventListener(type, handler) { this.handlers[type] = handler; },
        querySelector() { return null; },
        querySelectorAll() { return []; },
      });
    }
    return controls.get(selector);
  }
  control("#workflow-editor").value = JSON.stringify(workflow);
  control("#layer-names").value = "source";
  const context = createContext({
    console,
    document: { querySelector: control },
    fetch: async (path, options) => {
      calls.push({ path, body: options.body ? JSON.parse(options.body) : null });
      if (held.has(path)) {
        const pending = held.get(path);
        held.delete(path);
        pending.started();
        return pending.promise;
      }
      assert.ok(Object.hasOwn(fixtures, path), `unexpected endpoint: ${path}`);
      return reply(fixtures[path]);
    },
  });
  const facade = readFileSync(new URL("render.js", staticRoot), "utf8");
  const exports = [...facade.matchAll(/export\s*\{([^}]+)\}/g)]
    .flatMap((match) => match[1].split(",").map((name) => name.trim()).filter(Boolean));
  const renderer = new SyntheticModule(exports, function () {
    for (const name of exports) {
      this.setExport(name, (...args) => {
        rendered.push({ name, args });
        if (name === "setRequestStatus" || name === "setReviewState") {
          args[0].textContent = args[1];
        }
        if (name === "renderExecutionControls") {
          const [select, button, outputs, enabled] = args;
          select.value = outputs[0] || "";
          select.disabled = !enabled;
          button.disabled = !enabled;
        }
      });
    }
  }, { context, identifier: "render-double" });
  const modules = new Map([["render.js", renderer]]);
  function load(name) {
    if (!modules.has(name)) {
      assert.match(name, /^[a-z_]+\.js$/);
      modules.set(name, new SourceTextModule(readFileSync(new URL(name, staticRoot), "utf8"), {
        context, identifier: name,
      }));
    }
    return modules.get(name);
  }
  const app = load("app.js");
  await app.link((specifier) => {
    assert.ok(specifier.startsWith("./"));
    return load(specifier.slice(2));
  });
  await app.evaluate();
  await tick();
  const click = (selector) => control(selector).handlers.click();
  function editWorkflow() {
    control("#workflow-editor").value = JSON.stringify({ ...workflow, steps: [{ output: "edited" }] });
    control("#workflow-editor").handlers.input();
  }
  function editData(value = '{"changed":true}') {
    control("#preflight-inputs").handlers.input({
      target: { dataset: { preflightLayer: "source" }, value },
    });
  }
  function hold(name) {
    const path = pathFor(name);
    assert.ok(!held.has(path));
    let resolve, reject, started;
    const pending = {
      promise: new Promise((yes, no) => { resolve = yes; reject = no; }),
      wait: new Promise((yes) => { started = yes; }),
      started: () => started(),
      resolve: (payload = fixtures[path]) => resolve(reply(payload)),
      reject: () => reject(new Error("delayed transport failure")),
    };
    held.set(path, pending);
    return pending;
  }
  async function reviewed() { await click("#review-button"); }
  async function ready() {
    await reviewed();
    editData('{"original":true}');
    await click("#preflight-button");
    assert.equal(control("#execution-button").disabled, false);
  }
  return { control, click, hold, editWorkflow, editData, reviewed, ready, calls, rendered };
}

for (const endpoint of ["validate", "plan"]) {
  test(`editing Workflow while ${endpoint} is pending cannot restore old Review`, async () => {
    const h = await harness();
    const old = h.hold(endpoint);
    const request = h.click("#review-button");
    await old.wait;
    h.editWorkflow();
    old.resolve();
    await request;
    assert.equal(h.control("#review-state").textContent, "Not reviewed");
    assert.equal(h.control("#preflight-button").disabled, true);
    assert.equal(h.rendered.filter((call) => call.name === "renderReports").length, 0);
    if (endpoint === "validate") {
      assert.equal(h.calls.filter((call) => call.path === pathFor("plan")).length, 0);
    }
  });
}

test("editing only layer names invalidates pending Review", async () => {
  const h = await harness();
  const old = h.hold("plan");
  const request = h.click("#review-button");
  await old.wait;
  h.control("#layer-names").value = "other";
  h.control("#layer-names").handlers.input();
  old.resolve();
  await request;
  assert.equal(h.control("#review-state").textContent, "Not reviewed");
});

test("editing inline data while Preflight is pending cannot enable Execute", async () => {
  const h = await harness();
  await h.reviewed();
  h.editData();
  const old = h.hold("preflight");
  const request = h.click("#preflight-button");
  await old.wait;
  h.editData('{"newer":true}');
  old.resolve();
  await request;
  assert.equal(h.control("#execution-button").disabled, true);
  assert.equal(h.control("#review-state").textContent, "Reviewed");
  assert.equal(h.rendered.filter((call) => call.name === "renderPreflightReport").length, 0);
});

for (const stage of ["review", "preflight"]) {
  test(`starting another ${stage} clears previous downstream evidence immediately`, async () => {
    const h = await harness();
    await h.ready();
    await h.click("#execution-button");
    const old = h.hold(stage === "review" ? "validate" : "preflight");
    const before = h.rendered.length;
    const request = h.click(stage === "review" ? "#review-button" : "#preflight-button");
    await old.wait;
    assert.equal(h.control("#execution-button").disabled, true);
    const freshCalls = h.rendered.slice(before).map((call) => call.name);
    assert.ok(freshCalls.includes("resetResultPreview"));
    assert.ok(freshCalls.includes(stage === "review" ? "resetPreflightWorkspace" : "resetPreflightResult"));
    old.resolve();
    await request;
  });
}

for (const endpoint of ["validate", "preflight", "execute"]) {
  for (const outcome of ["resolve", "reject"]) {
    test(`late ${endpoint} ${outcome} cannot overwrite a newer successful run`, async () => {
      const h = await harness();
      await h.ready();
      const old = h.hold(endpoint);
      const button = endpoint === "validate" ? "#review-button"
        : endpoint === "preflight" ? "#preflight-button" : "#execution-button";
      const request = h.click(button);
      await old.wait;
      h.editWorkflow();
      await h.ready();
      await h.click("#execution-button");
      const before = h.rendered.length;
      old[outcome]();
      await request;
      assert.equal(h.rendered.length, before, "stale continuations must not render or reset anything");
      assert.equal(h.control("#execution-button").disabled, false);
      assert.equal(h.control("#review-state").textContent, "Reviewed");
    });
  }
}

for (const endpoint of ["validate", "preflight", "execute"]) {
  test(`old ${endpoint} finally cannot unlock controls owned by a newer request`, async () => {
    const h = await harness();
    await h.ready();
    const button = endpoint === "validate" ? "#review-button"
      : endpoint === "preflight" ? "#preflight-button" : "#execution-button";
    const old = h.hold(endpoint);
    const first = h.click(button);
    await old.wait;
    h.editWorkflow();
    if (endpoint !== "validate") await h.reviewed();
    if (endpoint === "execute") {
      h.editData();
      await h.click("#preflight-button");
    }
    const current = h.hold(endpoint);
    const second = h.click(button);
    await current.wait;
    old.resolve();
    await first;
    assert.equal(h.control(button).disabled, true);
    current.resolve();
    await second;
    assert.equal(h.control(button).disabled, false);
  });
}

test("rerunning execution removes old preview/manifest evidence before its response", async () => {
  const h = await harness();
  await h.ready();
  await h.click("#execution-button");
  const old = h.hold("execute");
  const before = h.rendered.length;
  const request = h.click("#execution-button");
  await old.wait;
  const calls = h.rendered.slice(before);
  assert.ok(calls.some((call) => call.name === "resetResultPreview"));
  assert.ok(calls.some((call) => call.name === "renderCrsEvidence" && call.args[3] === null));
  old.resolve();
  await request;
});

test("current transport failures remain visible and valid retries recover", async () => {
  const h = await harness();
  const failure = h.hold("validate");
  const request = h.click("#review-button");
  await failure.wait;
  failure.reject();
  await request;
  assert.equal(h.control("#review-state").textContent, "Review failed");
  assert.match(h.control("#request-status").textContent, /delayed transport failure/);
  await h.ready();
  await h.click("#execution-button");
  assert.equal(h.rendered.filter((call) => call.name === "renderExecutionResult").length, 1);
});
