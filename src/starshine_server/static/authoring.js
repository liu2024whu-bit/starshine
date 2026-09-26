import { renderInputContractGuidance } from "./guidance.js";
function hasOwn(object, key) {
  return Object.prototype.hasOwnProperty.call(object, key);
}

function requiredText(parameter) {
  return parameter.required ? "required" : "optional";
}

function parameterPlaceholder(parameter) {
  if (hasOwn(parameter, "default")) {
    return `Default from catalog: ${JSON.stringify(parameter.default)}`;
  }
  return parameter.required ? "Enter a JSON value" : "Blank omits this parameter";
}

function parseParameterValue(parameter, rawValue) {
  const text = rawValue.trim();
  if (!text) {
    if (parameter.required) {
      throw new Error(`Parameter ${parameter.name} is required by the catalog and needs a JSON value.`);
    }
    return { include: false, value: null };
  }

  try {
    return { include: true, value: JSON.parse(text) };
  } catch (error) {
    throw new Error(`Parameter ${parameter.name} is not valid JSON: ${error.message}`);
  }
}

export function buildCandidateStep(operator, draft) {
  if (!operator || typeof operator.name !== "string") {
    throw new Error("Select a catalog operator before inserting a step.");
  }

  const inputs = {};
  for (const input of Array.isArray(operator.inputs) ? operator.inputs : []) {
    const value = String(draft.inputs[input.name] ?? "").trim();
    if (!value) {
      throw new Error(`Input role ${input.name} needs a layer name.`);
    }
    inputs[input.name] = value;
  }

  const parameters = {};
  for (const parameter of Array.isArray(operator.parameters) ? operator.parameters : []) {
    const parsed = parseParameterValue(parameter, String(draft.parameters[parameter.name] ?? ""));
    if (parsed.include) {
      parameters[parameter.name] = parsed.value;
    }
  }

  const output = String(draft.output ?? "").trim();
  if (!output) {
    throw new Error("Output layer name is required.");
  }

  return {
    operation: operator.name,
    inputs,
    parameters,
    output,
  };
}

export function appendCandidateStep(workflow, step) {
  if (!workflow || typeof workflow !== "object" || Array.isArray(workflow)) {
    throw new Error("Workflow JSON must be an object before a step can be inserted.");
  }
  if (!Array.isArray(workflow.steps)) {
    throw new Error("Workflow JSON needs a steps array before a step can be inserted.");
  }

  return {
    ...workflow,
    steps: [...workflow.steps, step],
  };
}

function textElement(tag, text, className = "") {
  const element = document.createElement(tag);
  element.textContent = String(text);
  if (className) {
    element.className = className;
  }
  return element;
}

function fieldLabel(name, detail) {
  const label = document.createElement("label");
  label.appendChild(document.createTextNode(name));
  if (detail) {
    label.appendChild(textElement("span", ` ${detail}`, "label-note"));
  }
  return label;
}

function renderInputFields(container, operator) {
  while (container.firstChild) {
    container.removeChild(container.firstChild);
  }

  for (const input of Array.isArray(operator.inputs) ? operator.inputs : []) {
    const group = document.createElement("div");
    group.className = "builder-field";
    const controlId = `builder-input-${input.name}`;
    const label = fieldLabel(input.name, "layer name");
    label.htmlFor = controlId;
    group.appendChild(label);

    const control = document.createElement("input");
    control.id = controlId;
    control.className = "builder-control";
    control.type = "text";
    control.dataset.builderInput = input.name;
    control.autocomplete = "off";
    group.appendChild(control);

    if (input.description) {
      group.appendChild(textElement("p", input.description, "builder-help"));
    }
    renderInputContractGuidance(group, input.contract);
    container.appendChild(group);
  }
}

function renderParameterFields(container, operator) {
  while (container.firstChild) {
    container.removeChild(container.firstChild);
  }

  const parameters = Array.isArray(operator.parameters) ? operator.parameters : [];
  if (parameters.length === 0) {
    container.appendChild(textElement("p", "This catalog operator declares no parameters.", "muted"));
    return;
  }

  for (const parameter of parameters) {
    const group = document.createElement("div");
    group.className = "builder-field";
    const controlId = `builder-parameter-${parameter.name}`;
    const label = fieldLabel(parameter.name, requiredText(parameter));
    label.htmlFor = controlId;
    group.appendChild(label);

    const control = document.createElement("input");
    control.id = controlId;
    control.className = "builder-control builder-json-control";
    control.type = "text";
    control.dataset.builderParameter = parameter.name;
    control.autocomplete = "off";
    control.value = "";
    control.placeholder = parameterPlaceholder(parameter);
    group.appendChild(control);

    if (parameter.description) {
      group.appendChild(textElement("p", parameter.description, "builder-help"));
    }

    const schema = document.createElement("code");
    schema.className = "builder-schema";
    schema.textContent = `schema: ${JSON.stringify(parameter.schema)}`;
    group.appendChild(schema);
    container.appendChild(group);
  }
}

function selectedOperator(catalog, select) {
  const operators = Array.isArray(catalog.operators) ? catalog.operators : [];
  return operators.find((operator) => operator.name === select.value) ?? null;
}

function collectDraft(elements) {
  const inputs = {};
  for (const control of elements.inputs.querySelectorAll("[data-builder-input]")) {
    inputs[control.dataset.builderInput] = control.value;
  }

  const parameters = {};
  for (const control of elements.parameters.querySelectorAll("[data-builder-parameter]")) {
    parameters[control.dataset.builderParameter] = control.value;
  }

  return {
    inputs,
    parameters,
    output: elements.output.value,
  };
}

function renderOperator(catalog, elements) {
  const operator = selectedOperator(catalog, elements.operator);
  if (!operator) {
    elements.summary.textContent = "Choose an operator from the canonical catalog.";
    renderInputFields(elements.inputs, { inputs: [] });
    renderParameterFields(elements.parameters, { parameters: [] });
    elements.output.value = "";
    return;
  }

  elements.summary.textContent = operator.summary || "No catalog summary provided.";
  renderInputFields(elements.inputs, operator);
  renderParameterFields(elements.parameters, operator);
  elements.output.value = "";
}

export function initializeStepBuilder(catalog, elements, onInsert) {
  while (elements.operator.firstChild) {
    elements.operator.removeChild(elements.operator.firstChild);
  }

  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Choose an operator";
  elements.operator.appendChild(placeholder);

  for (const operator of Array.isArray(catalog.operators) ? catalog.operators : []) {
    const option = document.createElement("option");
    option.value = operator.name;
    option.textContent = operator.name;
    elements.operator.appendChild(option);
  }

  elements.operator.addEventListener("change", () => {
    renderOperator(catalog, elements);
    elements.status.textContent = "Builder fields come directly from the current catalog.";
    elements.status.classList.remove("is-error");
  });

  elements.insert.addEventListener("click", () => {
    try {
      const operator = selectedOperator(catalog, elements.operator);
      const step = buildCandidateStep(operator, collectDraft(elements));
      onInsert(step);
      elements.status.textContent = "Candidate step inserted. Review the Workflow to validate it.";
      elements.status.classList.remove("is-error");
    } catch (error) {
      elements.status.textContent = error.message;
      elements.status.classList.add("is-error");
    }
  });

  renderOperator(catalog, elements);
}
