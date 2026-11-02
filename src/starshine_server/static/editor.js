export function findCatalogOperator(catalog, name) {
  const operators = catalog && Array.isArray(catalog.operators) ? catalog.operators : [];
  return operators.find((operator) => operator && operator.name === name) || null;
}

export function layerSuggestions(workflow, externalLayerNames) {
  const suggestions = [];
  const seen = new Set();

  function add(value) {
    if (typeof value !== "string") {
      return;
    }
    const name = value.trim();
    if (!name || seen.has(name)) {
      return;
    }
    seen.add(name);
    suggestions.push(name);
  }

  if (Array.isArray(externalLayerNames)) {
    for (const name of externalLayerNames) {
      add(name);
    }
  }

  if (workflow && Array.isArray(workflow.steps)) {
    for (const step of workflow.steps) {
      if (step && typeof step === "object") {
        add(step.output);
      }
    }
  }

  return suggestions;
}

// Draft insertion reserializes JSON. Keep numeric representation bounded rather
// than silently turning overflow into null or rounding large integer values.
export function parseDraftJson(raw, label = "Draft JSON") {
  try {
    return JSON.parse(raw, (_key, value) => {
      if (typeof value === "number" && (
        !Number.isFinite(value) || (Number.isInteger(value) && !Number.isSafeInteger(value))
      )) {
        throw new Error("draft numbers must be finite and integer values must be within the browser safe-integer range");
      }
      return value;
    });
  } catch (error) {
    throw new Error(`${label} must be valid JSON within browser numeric limits: ${error.message}`);
  }
}

export function decodeDraftValue(rawValue, parameterName = "parameter") {
  const raw = typeof rawValue === "string" ? rawValue.trim() : "";
  if (!raw) {
    return { present: false, value: null };
  }
  return { present: true, value: parseDraftJson(raw, `Parameter ${parameterName}`) };
}

function setOwn(target, key, value) {
  Object.defineProperty(target, key, { value, enumerable: true, configurable: true, writable: true });
}

export function buildDraftStep(operator, inputValues, parameterValues, outputValue) {
  if (!operator || typeof operator.name !== "string") {
    throw new Error("Select a canonical operator before adding a draft step.");
  }

  const inputs = {};
  for (const input of Array.isArray(operator.inputs) ? operator.inputs : []) {
    if (!input || typeof input.name !== "string") {
      continue;
    }
    const value = inputValues && inputValues[input.name];
    if (typeof value === "string" && value.trim()) {
      setOwn(inputs, input.name, value.trim());
    }
  }

  const parameters = {};
  for (const parameter of Array.isArray(operator.parameters) ? operator.parameters : []) {
    if (!parameter || typeof parameter.name !== "string") {
      continue;
    }
    const decoded = decodeDraftValue(
      parameterValues && parameterValues[parameter.name],
      parameter.name,
    );
    if (decoded.present) {
      setOwn(parameters, parameter.name, decoded.value);
    }
  }

  return {
    operation: operator.name,
    inputs,
    parameters,
    output: typeof outputValue === "string" ? outputValue.trim() : "",
  };
}

export function appendDraftStep(workflow, step) {
  if (!workflow || typeof workflow !== "object" || Array.isArray(workflow)) {
    throw new Error("Workflow JSON must be an object before a step can be appended.");
  }
  if (!Array.isArray(workflow.steps)) {
    throw new Error("Workflow JSON must contain a steps array before a step can be appended.");
  }

  return {
    ...workflow,
    steps: [...workflow.steps, step],
  };
}
