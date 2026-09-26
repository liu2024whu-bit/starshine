function jsonText(value) {
  return JSON.stringify(value);
}

export function contractGuidanceRows(contract) {
  const value = contract && typeof contract === "object" ? contract : {};
  const geometryTypes = Array.isArray(value.geometry_types) ? value.geometry_types : [];
  const notes = Array.isArray(value.notes) ? value.notes : [];

  return {
    geometry: geometryTypes.length ? geometryTypes.join(", ") : "none declared",
    crs: jsonText(value.crs ?? {}),
    requiredFields: jsonText(Array.isArray(value.required_fields) ? value.required_fields : []),
    writtenFields: jsonText(Array.isArray(value.written_fields) ? value.written_fields : []),
    notes: notes.map((note) => String(note)),
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

function guidanceRow(label, value) {
  const row = document.createElement("div");
  row.className = "builder-guidance-row";
  row.appendChild(textElement("strong", label));
  row.appendChild(textElement("code", value));
  return row;
}

export function renderInputContractGuidance(container, contract) {
  const rows = contractGuidanceRows(contract);

  const details = document.createElement("details");
  details.className = "builder-guidance";

  const summary = document.createElement("summary");
  summary.textContent = "Unresolved catalog contract guidance";
  details.appendChild(summary);

  const body = document.createElement("div");
  body.className = "builder-guidance-body";
  body.appendChild(guidanceRow("Geometry types", rows.geometry));
  body.appendChild(guidanceRow("CRS contract", rows.crs));
  body.appendChild(guidanceRow("Required field declarations", rows.requiredFields));
  body.appendChild(guidanceRow("Written field declarations", rows.writtenFields));

  if (rows.notes.length) {
    const notes = document.createElement("div");
    notes.className = "builder-guidance-notes";
    notes.appendChild(textElement("strong", "Notes"));
    const list = document.createElement("ul");
    for (const note of rows.notes) {
      list.appendChild(textElement("li", note));
    }
    notes.appendChild(list);
    body.appendChild(notes);
  }

  const boundary = textElement(
    "p",
    "This is catalog metadata only. Insert and review the step to resolve parameter-driven requirements.",
    "builder-guidance-boundary",
  );
  body.appendChild(boundary);

  details.appendChild(body);
  container.appendChild(details);
}
