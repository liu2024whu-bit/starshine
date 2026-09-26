import {
  clearNode,
  helperText,
  metaChip,
  textElement,
} from "./dom.js";

export function populateOperatorSelect(select, catalog) {
  clearNode(select);
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Choose a canonical operator";
  select.appendChild(placeholder);

  const operators = catalog && Array.isArray(catalog.operators) ? catalog.operators : [];
  for (const operator of operators) {
    if (!operator || typeof operator.name !== "string") {
      continue;
    }
    const option = document.createElement("option");
    option.value = operator.name;
    option.textContent = operator.name;
    select.appendChild(option);
  }

  select.disabled = operators.length === 0;
}

function appendInputContractHints(container, input) {
  const contract = input && input.contract && typeof input.contract === "object"
    ? input.contract
    : null;
  if (!contract) {
    return;
  }

  const row = document.createElement("div");
  row.className = "field-meta";

  const geometryTypes = Array.isArray(contract.geometry_types) ? contract.geometry_types : [];
  row.appendChild(
    metaChip(geometryTypes.length ? `geometry: ${geometryTypes.join(" / ")}` : "geometry: any validated type"),
  );

  if (contract.crs && typeof contract.crs.mode === "string") {
    row.appendChild(metaChip(`CRS: ${contract.crs.mode}`));
    if (typeof contract.crs.equivalent_to_input === "string") {
      row.appendChild(metaChip(`CRS = ${contract.crs.equivalent_to_input}`));
    }
  }

  container.appendChild(row);

  for (const note of Array.isArray(contract.notes) ? contract.notes : []) {
    container.appendChild(helperText(note));
  }
}

function parameterDefaultText(parameter) {
  if (!parameter || !Object.hasOwn(parameter, "default")) {
    return null;
  }
  return JSON.stringify(parameter.default);
}

export function renderStepBuilder(container, operator, layerNames) {
  clearNode(container);

  if (!operator) {
    container.appendChild(
      textElement("p", "Choose an operator to see its canonical inputs and parameters.", "builder-empty"),
    );
    return;
  }

  const intro = document.createElement("div");
  intro.className = "builder-operator-summary";
  intro.appendChild(textElement("strong", operator.name));
  intro.appendChild(helperText(operator.summary || "No summary reported by the catalog."));
  intro.appendChild(helperText(`Output CRS behavior: ${operator.output_crs || "not reported"}`));
  container.appendChild(intro);

  const listId = "builder-layer-suggestions";
  const datalist = document.createElement("datalist");
  datalist.id = listId;
  for (const layerName of Array.isArray(layerNames) ? layerNames : []) {
    const option = document.createElement("option");
    option.value = layerName;
    datalist.appendChild(option);
  }
  container.appendChild(datalist);

  const inputs = Array.isArray(operator.inputs) ? operator.inputs : [];
  for (const [index, input] of inputs.entries()) {
    const field = document.createElement("div");
    field.className = "builder-field";
    const fieldId = `builder-input-${index}`;

    const label = document.createElement("label");
    label.htmlFor = fieldId;
    label.textContent = `Input · ${input.name}`;
    field.appendChild(label);

    const control = document.createElement("input");
    control.id = fieldId;
    control.className = "builder-control";
    control.type = "text";
    control.setAttribute("list", listId);
    control.dataset.stepInput = input.name;
    control.autocomplete = "off";
    field.appendChild(control);

    field.appendChild(helperText(input.description || "No input description reported."));
    appendInputContractHints(field, input);
    container.appendChild(field);
  }

  const parameters = Array.isArray(operator.parameters) ? operator.parameters : [];
  for (const [index, parameter] of parameters.entries()) {
    const field = document.createElement("div");
    field.className = "builder-field";
    const fieldId = `builder-parameter-${index}`;

    const labelRow = document.createElement("div");
    labelRow.className = "builder-label-row";
    const label = document.createElement("label");
    label.htmlFor = fieldId;
    label.textContent = `Parameter · ${parameter.name}`;
    labelRow.appendChild(label);

    const defaultText = parameterDefaultText(parameter);
    if (parameter.required) {
      labelRow.appendChild(metaChip("required"));
    } else if (defaultText !== null) {
      labelRow.appendChild(metaChip(`Core default: ${defaultText}`));
    } else {
      labelRow.appendChild(metaChip("optional"));
    }
    field.appendChild(labelRow);

    const control = document.createElement("input");
    control.id = fieldId;
    control.className = "builder-control";
    control.type = "text";
    control.dataset.stepParameter = parameter.name;
    control.autocomplete = "off";
    control.placeholder = parameter.required
      ? "Enter a draft value; Server validates it"
      : "Leave blank to let Core resolve the default/optional value";
    field.appendChild(control);

    field.appendChild(helperText(parameter.description || "No parameter description reported."));
    const schema = parameter.schema && typeof parameter.schema === "object"
      ? JSON.stringify(parameter.schema)
      : "{}";
    field.appendChild(textElement("code", `Schema: ${schema}`, "schema-hint"));
    container.appendChild(field);
  }

  const outputField = document.createElement("div");
  outputField.className = "builder-field";
  const outputLabel = document.createElement("label");
  outputLabel.htmlFor = "builder-output";
  outputLabel.textContent = "Output layer name";
  outputField.appendChild(outputLabel);

  const output = document.createElement("input");
  output.id = "builder-output";
  output.className = "builder-control";
  output.type = "text";
  output.dataset.stepOutput = "true";
  output.autocomplete = "off";
  output.placeholder = "e.g. analysis_result";
  outputField.appendChild(output);
  outputField.appendChild(
    helperText("The browser does not check collisions or naming rules; Server validation remains authoritative."),
  );
  container.appendChild(outputField);
}

export function updateLayerSuggestions(container, layerNames) {
  const datalist = container.querySelector("#builder-layer-suggestions");
  if (!datalist) {
    return;
  }
  clearNode(datalist);
  for (const layerName of Array.isArray(layerNames) ? layerNames : []) {
    const option = document.createElement("option");
    option.value = layerName;
    datalist.appendChild(option);
  }
}
