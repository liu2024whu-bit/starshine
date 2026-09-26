import fs from "node:fs";

const sourceUrl = new URL(
  "../src/starshine_server/static/guidance.js",
  import.meta.url,
);
const source = fs.readFileSync(sourceUrl, "utf8");
const moduleUrl =
  "data:text/javascript;base64," + Buffer.from(source, "utf8").toString("base64");
const { contractGuidanceRows } = await import(moduleUrl);

function assertEqual(actual, expected, message) {
  const actualJson = JSON.stringify(actual);
  const expectedJson = JSON.stringify(expected);
  if (actualJson !== expectedJson) {
    throw new Error(
      `${message}\nexpected: ${expectedJson}\nactual:   ${actualJson}`,
    );
  }
}

const contract = {
  geometry_types: ["Polygon", "MultiPolygon"],
  crs: {
    mode: "parameter",
    parameter: "source_reference",
    equivalent_to_input: "mask",
  },
  required_fields: [
    {
      parameter: "identifier_field",
      unique: true,
      non_null: true,
      finite_json_scalar: false,
    },
  ],
  written_fields: [
    {
      parameter: "output_field",
      collision_policy: "reject",
    },
  ],
  notes: [
    "Synthetic catalog note.",
  ],
};

assertEqual(
  contractGuidanceRows(contract),
  {
    geometry: "Polygon, MultiPolygon",
    crs: JSON.stringify(contract.crs),
    requiredFields: JSON.stringify(contract.required_fields),
    writtenFields: JSON.stringify(contract.written_fields),
    notes: ["Synthetic catalog note."],
  },
  "Guidance must present the catalog contract without resolving parameter-driven values.",
);

console.log("Workbench input-guidance pure-function checks passed.");
