import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

async function asset(name) {
  const source = readFileSync(new URL(`../../src/starshine_server/static/${name}`, import.meta.url));
  return import(`data:text/javascript;base64,${source.toString("base64")}`);
}
const { requiredLayerNames, unusedLayerNames, buildPreflightRequest, assertPreflightEvidence } =
  await asset("assurance.js");
const { ENDPOINTS, requestJson, responseJsonText } = await asset("api.js");

function reviewed(required = ["source"], unused = []) {
  return {
    plan: {
      workflow_digest: "workflow", plan_digest: "plan",
      declared_external_layers: [...required, ...unused],
      required_external_layers: required, unused_external_layers: unused,
    },
    contract: { contract_digest: "contract", plan_digest: "plan" },
  };
}

test("inline slots use canonical required and unused names, not Workflow guesses", () => {
  const reports = reviewed(["source", "__proto__", "constructor"], ["unused"]);
  reports.contract.layers = [{ name: "not-a-slot", required: true }];
  assert.deepEqual(requiredLayerNames(reports), ["source", "__proto__", "constructor"]);
  assert.deepEqual(unusedLayerNames(reports), ["unused"]);
  assert.deepEqual(requiredLayerNames(null), []);
  assert.deepEqual(unusedLayerNames(null), []);
});

test("Preflight requires Review and rejects unused declarations instead of changing their evidence", () => {
  assert.throws(() => buildPreflightRequest("{}", null, new Map()), /Review/);
  const reports = reviewed(["source"], ["unused"]);
  const before = JSON.stringify(reports);
  assert.throws(() => buildPreflightRequest("{}", reports, new Map([
    ["source", "{}"], ["unused", "{}"],
  ])), /unused.*Review/i);
  assert.equal(JSON.stringify(reports), before);
});

test("blank and missing required drafts are omitted, without fake collections or extra drafts", () => {
  const reports = reviewed(["empty", "blank", "missing", "present"]);
  const drafts = new Map([
    ["empty", ""], ["blank", " \n\t"], ["present", " {}\n"],
    ["unrelated", "not even valid JSON"],
  ]);
  const before = [...drafts];
  assert.deepEqual(buildPreflightRequest(" {} ", reports, drafts), {
    method: "POST", workflowText: " {} ", layerTexts: [["present", " {}\n"]],
  });
  assert.deepEqual([...drafts], before);
  assert.deepEqual(buildPreflightRequest("{}", reviewed(), new Map()).layerTexts, []);
});

test("inline transport preserves Workflow and layer tokens and safely quotes every name", async () => {
  const workflowText = ' \n{"version":1.0,"values":[-0.0,9007199254740993,1e400]}\t';
  const names = ["__proto__", "constructor", 'quote"', "back\\slash", "河流😀", "line\nbreak"];
  const raw = ' \n{"type":"FeatureCollection","values":[1.0,-0.0,9007199254740993,1e400],"quoted":"\\\"},\\\"layers\\\":{}"}\t';
  const drafts = new Map(names.map((name) => [name, raw]));
  let sent;
  globalThis.fetch = async (path, init) => {
    sent = { path, ...init };
    return { ok: true, text: async () => '{"valid":true}' };
  };
  await requestJson(ENDPOINTS.preflight, buildPreflightRequest(workflowText, reviewed(names), drafts));
  assert.equal(sent.path, "/api/v1/workflows/preflight");
  assert.equal(sent.method, "POST");
  assert.equal(sent.headers["content-type"], "application/json");
  assert.equal(sent.credentials, "same-origin");
  assert.equal(sent.body,
    `{"workflow":${workflowText},"layers":{${names.map((name) => `${JSON.stringify(name)}:${raw}`).join(",")}}}`);
  const body = JSON.parse(sent.body);
  assert.deepEqual(Object.keys(body), ["workflow", "layers"]);
  assert.deepEqual(Object.keys(body.layers), names);
  assert.equal(Object.hasOwn(body.layers, "__proto__"), true);
  assert.equal(Object.getPrototypeOf(body.layers), Object.prototype);
});

test("valid JSON of any root shape reaches Server without browser GIS validation", async () => {
  const values = ["null", "[]", "1.0", "true", '"not GeoJSON"', "{}",
    '{"type":"FeatureCollection","features":"wrong"}',
    '{"type":"FeatureCollection","features":[],"starshine:crs":"invalid CRS"}',
    '{"nested":' + "[".repeat(66) + "0" + "]".repeat(66) + "}",
    " ".repeat(2 * 1024 * 1024) + "{}",
  ];
  const sent = [];
  globalThis.fetch = async (_path, init) => {
    sent.push(init.body);
    return { ok: false, status: 422, text: async () => '{"message":"Server owns this rejection"}' };
  };
  for (const raw of values) {
    const request = buildPreflightRequest("{}", reviewed(), new Map([["source", raw]]));
    await assert.rejects(requestJson(ENDPOINTS.preflight, request), /Server owns this rejection/);
    assert.equal(sent.at(-1), `{"workflow":{},"layers":{"source":${raw}}}`);
  }
  assert.equal(sent.length, values.length);
});

test("malformed layer JSON and envelope injection never reach fetch", async () => {
  globalThis.fetch = () => { throw new Error("fetch must not run"); };
  for (const raw of ["{", '[1,]', '{"x":1},"injected":{}', '{"x":NaN}']) {
    assert.throws(() => buildPreflightRequest("{}", reviewed(), new Map([["source", raw]])),
      /Layer.*source.*JSON/);
    await assert.rejects(requestJson(ENDPOINTS.preflight, {
      workflowText: "{}", layerTexts: [["source", raw]],
    }));
  }
  for (const layerTexts of [{ source: "{}" }, [["source", {}]], [[1, "{}"]],
    [["source", "{}"], ["source", "{}"]], [["source"]]]) {
    await assert.rejects(requestJson(ENDPOINTS.preflight, { workflowText: "{}", layerTexts }),
      /Layer drafts/);
  }
});

test("Preflight accepts canonical PASS and FAIL only within the current evidence chain", () => {
  const reports = reviewed();
  for (const valid of [true, false]) {
    assert.doesNotThrow(() => assertPreflightEvidence({
      valid, workflow_digest: "workflow", plan_digest: "plan", contract_digest: "contract",
    }, reports));
  }
  for (const field of ["workflow_digest", "plan_digest", "contract_digest"]) {
    for (const value of [undefined, null, 1, "other-review"]) {
      const report = { workflow_digest: "workflow", plan_digest: "plan", contract_digest: "contract" };
      report[field] = value;
      assert.throws(() => assertPreflightEvidence(report, reports), /evidence chain.*Review again/);
    }
  }
  assert.throws(() => assertPreflightEvidence({}, null), /Review/);
});

test("canonical Preflight response text is retained exactly beside its convenience object", async () => {
  const raw = ' \n{"valid":false,"findings":[{"message":"<img src=x onerror=alert(1)>"}],"values":[1.0,-0.0,9007199254740993]}\t';
  globalThis.fetch = async () => ({ ok: true, text: async () => raw });
  const response = await requestJson(ENDPOINTS.preflight, {
    method: "POST", workflowText: "{}", layerTexts: [["source", "{}"]],
  });
  assert.equal(responseJsonText(response), raw);
  assert.equal(response.valid, false);
});
