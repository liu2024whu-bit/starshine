function textElement(tag, text, className = "") {
  const element = document.createElement(tag);
  element.textContent = String(text);
  if (className) {
    element.className = className;
  }
  return element;
}

function catalogOperators(catalog) {
  return catalog && Array.isArray(catalog.operators) ? catalog.operators : [];
}

function operatorByName(catalog, name) {
  return catalogOperators(catalog).find((operator) => operator.name === name) || null;
}

function parameterGuidance(parameter) {
  const details = [];
  details.push(parameter.required ? "required by Core" : "optional");
  if (Object.prototype.hasOwnProperty.call(parameter, "default")) {
    details.push(`Core default: ${JSON.stringify(parameter.default)}`);
  }
  if (parameter.schema && typeof parameter.schema === "object") {
    details.push(`schema: ${JSON.stringify(parameter.schema)}`);
  }
  return details.join(" · ");
}

function buildTextField(labelText, description, name) {
  const wrapper = document.createElement("div");
  wrapper.className = "composer-field";

  const label = textElement("label", labelText);
  label.htmlFor = name;
  wrapper.appendChild(label);

  if (description) {
    wrapper.appendChild(textElement("p", description, "composer-help"));
  }

  const input = document.createElement("input");
  input.id = name;
  input.name = name;
  input.type = "text";
  input.autocomplete = "off";
  input.spellcheck = false;
  wrapper.appendChild(input);
  return { wrapper, input };
}

function buildParameterField(parameter, index) {
  const wrapper = document.createElement("div");
  wrapper.className = "composer-field";

  const fieldId = `composer-parameter-${index}`;
  const label = textElement(
    "label",
    parameter.required ? `${parameter.name} · required` : parameter.name,
  );
  label.htmlFor = fieldId;
  wrapper.appendChild(label);
  wrapper.appendChild(textElement("p", parameter.description || "", "composer-help"));
  wrapper.appendChild(textElement("p", parameterGuidance(parameter), "composer-meta"));

  const input = document.createElement("textarea");
  input.id = fieldId;
  input.className = "parameter-editor";
  input.rows = 2;
  input.spellcheck = false;
  input.placeholder = 'JSON value, e.g. 100, "EPSG:4326", true, or null';
  input.dataset.parameterName = parameter.name;
  wrapper.appendChild(input);
  return wrapper;
}

export function buildStepDraft(operator, inputValues, parameterValues, outputName) {
  if (!operator || typeof operator.name !== "string") {
    throw new Error("Select a catalog operator before composing a step.");
  }

  const inputs = {};
  for (const input of Array.isArray(operator.inputs) ? operator.inputs : []) {
    const value = String(inputValues[input.name] || "").trim();
    if (!value) {
      throw new Error(`Input role ${input.name} needs a layer name before the step can be added.`);
    }
    inputs[input.name] = value;
  }

  const output = String(outputName || "").trim();
  if (!output) {
    throw new Error("The composed step needs an output layer name.");
  }

  const parameters = {};
  for (const parameter of Array.isArray(operator.parameters) ? operator.parameters : []) {
    const raw = String(parameterValues[parameter.name] || "").trim();
    if (!raw) {
      continue;
    }
    try {
      parameters[parameter.name] = JSON.parse(raw);
    } catch (error) {
      throw new Error(
        `Parameter ${parameter.name} must be entered as one valid JSON value: ${error.message}`,
      );
    }
  }

  return {
    operation: operator.name,
    inputs,
    parameters,
    output,
  };
}

export function initializeStepComposer({
  catalog,
  select,
  details,
  fields,
  output,
  status,
  addButton,
  onAdd,
}) {
  const operators = catalogOperators(catalog);
  select.replaceChildren();

  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Choose an operator…";
  select.appendChild(placeholder);

  for (const operator of operators) {
    const option = document.createElement("option");
    option.value = operator.name;
    option.textContent = operator.name;
    select.appendChild(option);
  }

  function renderSelectedOperator() {
    fields.replaceChildren();
    output.value = "";
    const operator = operatorByName(catalog, select.value);
    if (!operator) {
      details.textContent = "Choose an operator to see canonical inputs and parameters.";
      addButton.disabled = true;
      return;
    }

    details.textContent = `${operator.summary} Output CRS: ${operator.output_crs}. ${operator.deterministic ? "Deterministic." : "Determinism not declared."}`;

    const inputHeading = textElement("h4", "Input roles", "composer-subheading");
    fields.appendChild(inputHeading);
    for (const [index, input] of (operator.inputs || []).entries()) {
      const field = buildTextField(
        input.name,
        input.description || "",
        `composer-input-${index}`,
      );
      field.input.dataset.inputRole = input.name;
      fields.appendChild(field.wrapper);
    }

    const parameterHeading = textElement("h4", "Parameters", "composer-subheading");
    fields.appendChild(parameterHeading);
    if (!operator.parameters || operator.parameters.length === 0) {
      fields.appendChild(
        textElement(
          "p",
          "This catalog operator has no parameters. The browser adds none.",
          "composer-help",
        ),
      );
    } else {
      for (const [index, parameter] of operator.parameters.entries()) {
        fields.appendChild(buildParameterField(parameter, index));
      }
    }

    addButton.disabled = false;
  }

  select.addEventListener("change", renderSelectedOperator);
  addButton.addEventListener("click", () => {
    const operator = operatorByName(catalog, select.value);
    if (!operator) {
      status.textContent = "Choose an operator first.";
      return;
    }

    const inputValues = {};
    for (const input of fields.querySelectorAll("[data-input-role]")) {
      inputValues[input.dataset.inputRole] = input.value;
    }

    const parameterValues = {};
    for (const input of fields.querySelectorAll("[data-parameter-name]")) {
      parameterValues[input.dataset.parameterName] = input.value;
    }

    try {
      const step = buildStepDraft(operator, inputValues, parameterValues, output.value);
      onAdd(step);
      status.textContent =
        "Step added to the Workflow JSON. Canonical validation has not run yet.";
    } catch (error) {
      status.textContent = error.message;
    }
  });

  renderSelectedOperator();
}
