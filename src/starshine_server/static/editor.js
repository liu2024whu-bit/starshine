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

export function decodeDraftValue(rawValue) {
  const raw = typeof rawValue === "string" ? rawValue.trim() : "";
  if (!raw) {
    return { present: false, value: null };
  }

  try {
    return { present: true, value: JSON.parse(raw) };
  } catch {
    return { present: true, value: raw };
  }
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
      inputs[input.name] = value.trim();
    }
  }

  const parameters = {};
  for (const parameter of Array.isArray(operator.parameters) ? operator.parameters : []) {
    if (!parameter || typeof parameter.name !== "string") {
      continue;
    }
    const decoded = decodeDraftValue(parameterValues && parameterValues[parameter.name]);
    if (decoded.present) {
      parameters[parameter.name] = decoded.value;
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
