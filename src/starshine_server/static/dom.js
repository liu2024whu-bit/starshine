export function clearNode(node) {
  while (node.firstChild) {
    node.removeChild(node.firstChild);
  }
}

export function textElement(tag, text, className = "") {
  const element = document.createElement(tag);
  element.textContent = String(text);
  if (className) {
    element.className = className;
  }
  return element;
}

export function formatList(values) {
  return Array.isArray(values) && values.length ? values.join(", ") : "none";
}

export function summaryCard(label, value) {
  const card = document.createElement("div");
  card.className = "summary-card";
  card.appendChild(textElement("div", label, "label"));
  card.appendChild(textElement("div", value, "value"));
  return card;
}

export function digestRow(label, value) {
  const row = document.createElement("div");
  row.className = "digest-row";
  row.appendChild(textElement("strong", label));
  row.appendChild(textElement("code", value || "not reported"));
  return row;
}

export function appendList(card, label, values) {
  card.appendChild(textElement("p", label));
  const list = document.createElement("ul");
  list.className = "report-list";
  if (!Array.isArray(values) || values.length === 0) {
    list.appendChild(textElement("li", "none"));
  } else {
    for (const value of values) {
      list.appendChild(textElement("li", value));
    }
  }
  card.appendChild(list);
}

export function helperText(text) {
  return textElement("p", text, "field-help");
}

export function metaChip(text) {
  return textElement("span", text, "meta-chip");
}
