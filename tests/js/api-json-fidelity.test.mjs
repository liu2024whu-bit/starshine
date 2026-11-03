import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../../src/starshine_server/static/api.js", import.meta.url));
const { requestJson, responseJsonText } = await import(`data:text/javascript;base64,${source.toString("base64")}`);

test("transport preserves original workflow tokens and escapes only layer names", async () => {
  const workflowText = ' \n{"version":1.0,"values":[8.0,-0.0,9007199254740993,1e400],"quoted":"\\\"},\\\"layer_names\\\":[1]"}\t';
  const layerNames = ['quote"', 'back\\slash', 'line\nbreak', '__proto__'];
  let sent;
  globalThis.fetch = async (_path, init) => {
    sent = init;
    return { ok: true, text: async () => '{"valid":true}' };
  };
  await requestJson("/review", { method: "POST", workflowText, layerNames });
  assert.equal(sent.body, `{"workflow":${workflowText},"layer_names":${JSON.stringify(layerNames)}}`);
  assert.deepEqual(JSON.parse(sent.body).layer_names, layerNames);
  assert.deepEqual(Object.keys(JSON.parse(sent.body)), ["workflow", "layer_names"]);
  assert.equal(sent.headers["content-type"], "application/json");
  assert.equal(sent.credentials, "same-origin");
});

test("invalid JSON, envelope injection and non-object roots never reach fetch", async () => {
  globalThis.fetch = () => { throw new Error("fetch must not run"); };
  for (const workflowText of ['{', '{"x":1},"layer_names":["injected"]', 'null', '[]', '1', '"text"']) {
    await assert.rejects(requestJson("/review", { workflowText, layerNames: [] }), /Workflow JSON/);
  }
  await assert.rejects(requestJson("/review", { workflowText: {}, layerNames: [] }), /must be text/);
  for (const layerNames of ["layer", [1], [null], {}]) {
    await assert.rejects(requestJson("/review", { workflowText: "{}", layerNames }), /array of strings/);
  }
});

test("response text is retained exactly independently of convenience parsing", async () => {
  const raw = ' {\n "value":9007199254740993,"nested":[-0.0,8.0],"html":"<img src=x onerror=alert(1)>"\n}\t';
  globalThis.fetch = async () => ({ ok: true, text: async () => raw });
  const payload = await requestJson("/review");
  assert.equal(responseJsonText(payload), raw);
  assert.equal(payload.value, 9007199254740992);
  assert.equal(responseJsonText({}), undefined);
});

test("transport retains HTTP errors and rejects malformed response objects", async () => {
  globalThis.fetch = async () => ({ ok: false, status: 422,
    text: async () => '{"diagnostic":{"message":"Core rejection"}}' });
  await assert.rejects(requestJson("/review"), /Core rejection/);
  for (const raw of ['{', 'null', '[]', '"string"']) {
    globalThis.fetch = async () => ({ ok: true, text: async () => raw });
    await assert.rejects(requestJson("/review"), /non-JSON|invalid JSON object/);
  }
});
