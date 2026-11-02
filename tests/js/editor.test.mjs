import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
const source = readFileSync(new URL("../../src/starshine_server/static/editor.js", import.meta.url));
const { appendDraftStep, buildDraftStep, decodeDraftValue, findCatalogOperator, layerSuggestions, parseDraftJson } =
  await import(`data:text/javascript;base64,${source.toString("base64")}`);
const operator = { name: "synthetic_catalog_entry", inputs: [{ name: "left" }, { name: "right" }],
  parameters: [{ name: "number", required: true }, { name: "text" }, { name: "flag", default: true },
    { name: "array" }, { name: "object" }, { name: "nullable" }] };

test("generic operator maps roles and JSON types without injecting untouched defaults", () => {
  const inputs = { left: " source ", right: "prior", unexpected: "ignore" };
  const parameters = { number: "2.5", text: '"literal"', flag: "", array: "[1,false]",
    object: '{"key":3}', nullable: "null", unexpected: "1" };
  const before = JSON.stringify({ operator, inputs, parameters });
  assert.deepEqual(buildDraftStep(operator, inputs, parameters, " output "), {
    operation: operator.name, inputs: { left: "source", right: "prior" },
    parameters: { number: 2.5, text: "literal", array: [1, false], object: { key: 3 }, nullable: null },
    output: "output",
  });
  assert.equal(JSON.stringify({ operator, inputs, parameters }), before);
  assert.deepEqual(buildDraftStep(operator, {}, {}, "").parameters, {});
  assert.deepEqual(decodeDraftValue("false"), { present: true, value: false });
  assert.deepEqual(decodeDraftValue("  "), { present: false, value: null });
});

test("nonempty malformed JSON never silently becomes text", () => {
  for (const value of ["EPSG:4326", "NaN", "Infinity", "1e400", "[1e400]", '{"x":1e400}', "{", "[1,]", '"unterminated']) {
    assert.throws(() => decodeDraftValue(value, "example"), /Parameter example must be valid JSON/);
    assert.throws(() => buildDraftStep(operator, {}, { text: value }, "out"), /valid JSON/);
  }
});

test("suggestions are deduplicated declared then produced names, not dependency validation", () => {
  assert.deepEqual(layerSuggestions({ steps: [{ output: "produced" }, { output: "source" },
    null, { output: 2 }, { output: "future" }] }, [" source ", "external", "", "source"]),
  ["source", "external", "produced", "future"]);
  assert.deepEqual(layerSuggestions(null, ["external"]), ["external"]);
  assert.equal(findCatalogOperator({ operators: [operator] }, operator.name), operator);
  assert.equal(findCatalogOperator(null, "missing"), null);
});

test("append is nonmutating, preserves metadata, and does not claim semantic validation", () => {
  const workflow = { version: 1, metadata: { note: "keep" }, steps: [{ operation: "existing" }] };
  const before = JSON.stringify(workflow);
  const draft = buildDraftStep(operator, {}, {}, "");
  const updated = appendDraftStep(workflow, draft);
  assert.equal(JSON.stringify(workflow), before);
  assert.notEqual(updated, workflow);
  assert.notEqual(updated.steps, workflow.steps);
  assert.deepEqual(updated, { ...workflow, steps: [...workflow.steps, draft] });
  for (const invalid of [null, [], false, "", {}, { steps: null }, { steps: {} }]) {
    assert.throws(() => appendDraftStep(invalid, draft), /Workflow JSON/);
  }
  assert.throws(() => buildDraftStep(null, {}, {}, ""), /canonical operator/);
});


test("draft JSON rejects nested overflow and unsafe integers, preserves safe boundaries", () => {
  for (const token of ["1e400", "-1e400", "9007199254740993", "-9007199254740993"]) {
    for (const raw of [token, `[${token}]`, `{"nested":{"value":${token}}}`]) {
      assert.throws(() => parseDraftJson(raw), /browser numeric limits/);
      assert.throws(() => decodeDraftValue(raw), /browser numeric limits/);
    }
  }
  for (const value of [Number.MAX_SAFE_INTEGER, Number.MIN_SAFE_INTEGER, 0, 1.25, -0.5]) {
    assert.equal(parseDraftJson(String(value)), value);
    assert.equal(decodeDraftValue(String(value)).value, value);
  }
});

test("catalog roles and parameters named __proto__ remain own serialized properties", () => {
  const unusual = { name: "generic", inputs: [{ name: "__proto__" }],
    parameters: [{ name: "__proto__" }] };
  const inputs = JSON.parse('{"__proto__":"source"}');
  const parameters = Object.create(null);
  parameters.__proto__ = '{"nested":true}';
  const draft = buildDraftStep(unusual, inputs, parameters, "__proto__");
  assert.equal(Object.hasOwn(draft.inputs, "__proto__"), true);
  assert.equal(Object.hasOwn(draft.parameters, "__proto__"), true);
  assert.equal(Object.getPrototypeOf(draft.inputs), Object.prototype);
  assert.equal(Object.getPrototypeOf(draft.parameters), Object.prototype);
  assert.equal(draft.inputs.__proto__, "source");
  assert.deepEqual(draft.parameters.__proto__, { nested: true });
  assert.deepEqual(JSON.parse(JSON.stringify(draft)), {
    operation: "generic", inputs, parameters: JSON.parse('{"__proto__":{"nested":true}}'),
    output: "__proto__",
  });
});
