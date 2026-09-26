import fs from "node:fs";

const sourceUrl = new URL(
  "../src/starshine_server/static/authoring.js",
  import.meta.url,
);
const source = fs.readFileSync(sourceUrl, "utf8");
const moduleUrl =
  "data:text/javascript;base64," + Buffer.from(source, "utf8").toString("base64");
const { appendCandidateStep, buildCandidateStep } = await import(moduleUrl);

function assertEqual(actual, expected, message) {
  const actualJson = JSON.stringify(actual);
  const expectedJson = JSON.stringify(expected);
  if (actualJson !== expectedJson) {
    throw new Error(
      `${message}\nexpected: ${expectedJson}\nactual:   ${actualJson}`,
    );
  }
}

const catalogOperator = {
  name: "synthetic_operator",
  inputs: [
    {
      name: "source",
      description: "Synthetic source role.",
    },
  ],
  parameters: [
    {
      name: "required_value",
      description: "Required raw JSON value.",
      required: true,
      schema: { type: "object" },
    },
    {
      name: "optional_value",
      description: "Optional raw JSON value.",
      required: false,
      schema: { type: "number" },
    },
    {
      name: "defaulted_value",
      description: "Value whose catalog default would prefill the UI.",
      required: false,
      default: 5,
      schema: { type: "integer" },
    },
  ],
};

const candidate = buildCandidateStep(catalogOperator, {
  inputs: {
    source: "external_source",
  },
  parameters: {
    required_value: '{"mode":"review"}',
    optional_value: "",
    defaulted_value: "5",
  },
  output: "candidate_output",
});

assertEqual(
  candidate,
  {
    operation: "synthetic_operator",
    inputs: {
      source: "external_source",
    },
    parameters: {
      required_value: { mode: "review" },
      defaulted_value: 5,
    },
    output: "candidate_output",
  },
  "Candidate step must reflect catalog roles plus user-entered JSON values.",
);

const workflow = appendCandidateStep(
  {
    version: 1,
    steps: [],
  },
  candidate,
);

assertEqual(
  workflow.steps,
  [candidate],
  "Candidate step must append to the visible Workflow model.",
);

let requiredFailure = null;
try {
  buildCandidateStep(catalogOperator, {
    inputs: { source: "external_source" },
    parameters: {
      required_value: "",
      optional_value: "",
      defaulted_value: "5",
    },
    output: "candidate_output",
  });
} catch (error) {
  requiredFailure = error;
}
if (!(requiredFailure instanceof Error)) {
  throw new Error("Blank catalog-required parameter must stop candidate insertion.");
}

let jsonFailure = null;
try {
  buildCandidateStep(catalogOperator, {
    inputs: { source: "external_source" },
    parameters: {
      required_value: "{not-json}",
      optional_value: "",
      defaulted_value: "5",
    },
    output: "candidate_output",
  });
} catch (error) {
  jsonFailure = error;
}
if (!(jsonFailure instanceof Error)) {
  throw new Error("Invalid JSON parameter text must stop candidate insertion.");
}

console.log("Workbench authoring pure-function checks passed.");
