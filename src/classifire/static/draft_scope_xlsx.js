"use strict";

(() => {
  const form = document.getElementById("xlsx-mapping-form");
  if (!form) return;
  const error = document.getElementById("xlsx-mapping-error");
  const sheetSelect = document.getElementById("xlsx-sheet");
  const headerInput = document.getElementById("xlsx-header");
  const startInput = document.getElementById("xlsx-start-row");
  const mappingInputs = [...form.querySelectorAll("[data-map-field]")];
  const selected = new Map();
  let documentData, sheet, cells, start = Number(form.dataset.startRow) || 1, dirty = false;
  function node(tag, text, className) {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (className) item.className = className;
    return item;
  }
  function problem(message) { error.textContent = message; error.hidden = false; }
  function letter(number) {
    let result = "";
    for (let value = number; value > 0; value = Math.floor((value - 1) / 26)) result = String.fromCharCode(65 + (value - 1) % 26) + result;
    return result;
  }
  function refreshMapping() {
    const header = Number(headerInput.value);
    mappingInputs.forEach((input) => {
      const prior = input.value;
      input.replaceChildren(new Option("Unknown / not mapped", ""));
      for (let col = 1; col <= sheet.columns; col += 1) {
        const value = cells.get(`${header}:${col}`)?.value;
        input.append(new Option(`${letter(col)}${value != null ? " - " + String(value).slice(0, 90) : ""}`, String(col)));
      }
      input.value = prior;
    });
  }
  function refreshSelection() {
    const container = document.getElementById("xlsx-selected-rows");
    container.replaceChildren(node("p", `${selected.size} of 25 rows selected for this batch.`, "scope-hint"));
    [...selected.entries()].sort((a, b) => a[0] - b[0]).forEach(([row, kinds]) => {
      const button = node("button", `Remove row ${row} (${[...kinds].join(", ")})`, "button button-secondary");
      button.type = "button";
      button.addEventListener("click", () => { selected.delete(row); dirty = true; renderRows(); });
      container.append(button);
    });
  }
  function renderRows() {
    start = Math.max(1, Math.min(start, sheet.rows));
    startInput.value = String(start);
    const end = Math.min(start + 24, sheet.rows);
    document.getElementById("xlsx-row-status").textContent = `${sheet.name}: showing rows ${start}-${end} of ${sheet.rows}. Rows at or above the chosen header cannot be selected.`;
    const table = node("table"), head = node("thead"), headRow = node("tr");
    ["Row", "Draft item kinds", ...Array.from({ length: sheet.columns }, (_, i) => letter(i + 1))].forEach((text) => headRow.append(node("th", text)));
    head.append(headRow); table.append(head);
    const body = node("tbody");
    for (let row = start; row <= end; row += 1) {
      const tr = node("tr"); tr.append(node("th", String(row)));
      const kindsCell = node("td");
      ["defect", "opening", "service"].forEach((kind) => {
        const label = node("label", undefined, "scope-check");
        const checkbox = node("input"); checkbox.type = "checkbox";
        checkbox.id = `xlsx-row-${row}-${kind}`; label.htmlFor = checkbox.id;
        checkbox.setAttribute("aria-label", `Draft ${kind} from row ${row}`);
        checkbox.checked = selected.get(row)?.has(kind) || false;
        checkbox.disabled = row <= Number(headerInput.value);
        checkbox.addEventListener("change", () => {
          if (checkbox.checked && !selected.has(row) && selected.size >= 25) {
            checkbox.checked = false; problem("Select at most 25 rows in one reviewed batch. Remove a selected row before adding another."); return;
          }
          const choices = selected.get(row) || new Set();
          if (checkbox.checked) choices.add(kind); else choices.delete(kind);
          if (choices.size) selected.set(row, choices); else selected.delete(row);
          dirty = true; error.hidden = true; refreshSelection();
        });
        label.append(checkbox, document.createTextNode(kind)); kindsCell.append(label);
      });
      tr.append(kindsCell);
      for (let col = 1; col <= sheet.columns; col += 1) {
        const td = node("td"), cell = cells.get(`${row}:${col}`);
        if (cell) {
          const details = node("details");
          details.append(node("summary", `${cell.address} (${cell.kind}): ${String(cell.value).slice(0, 100)}${String(cell.value).length > 100 ? "..." : ""}`));
          details.append(node("div", String(cell.value), "scope-preserve-text")); td.append(details);
        } else td.append(node("span", `${letter(col)}${row}: blank`, "scope-hint"));
        tr.append(td);
      }
      body.append(tr);
    }
    table.append(body); document.getElementById("xlsx-grid").replaceChildren(table);
    document.getElementById("xlsx-previous").disabled = start === 1;
    document.getElementById("xlsx-next").disabled = end === sheet.rows;
    refreshSelection();
  }
  function renderImages() {
    const container = document.getElementById("xlsx-source-images"); container.replaceChildren();
    (sheet.images || []).forEach((image, index) => {
      const figure = node("figure"), link = node("a"), img = node("img");
      link.href = `${form.dataset.sourceUrl}/images/${sheet.index}/${encodeURIComponent(image.occurrence_id)}.png`;
      link.target = "_blank"; link.rel = "noopener";
      img.src = link.href; img.alt = `Worksheet image ${index + 1}`; img.loading = "lazy";
      link.append(img); const anchor = image.anchor;
      const start = `${letter(anchor.from.column)}${anchor.from.row}`;
      const end = anchor.to ? ` to ${letter(anchor.to.column)}${anchor.to.row}` : "";
      figure.append(link, node("figcaption", `Image ${index + 1} (${image.occurrence_id}). Placed at ${start}${end}; placement is context only.`));
      const details = node("details"); details.append(node("summary", "Image identity and worksheet anchor"));
      details.append(node("p", image.occurrence_id, "scope-item-id"), node("pre", JSON.stringify(image.anchor, null, 2), "pdf-recovery-json"));
      figure.append(details); container.append(figure);
    });
    if (!(sheet.images || []).length) container.append(node("p", "No retained images on this worksheet.", "scope-empty"));
  }
  function setSheet(index) {
    sheet = documentData.sheets.find((item) => item.index === index);
    if (!sheet) throw new Error("Worksheet unavailable");
    cells = new Map(sheet.cells.map((cell) => [`${cell.row}:${cell.column}`, cell]));
    sheetSelect.value = String(sheet.index); startInput.max = String(sheet.rows);
    headerInput.max = String(Math.max(1, sheet.rows - 1));
    refreshMapping(); renderRows(); renderImages();
  }
  try {
    documentData = JSON.parse(document.getElementById("xlsx-initial-document").textContent);
    const plan = JSON.parse(document.getElementById("xlsx-initial-plan").textContent);
    for (const entry of plan.selections || []) selected.set(entry.row, new Set(entry.kinds));
    setSheet(plan.sheet_index);
    mappingInputs.forEach((input) => { input.value = plan.mapping[input.dataset.mapField] == null ? "" : String(plan.mapping[input.dataset.mapField]); input.addEventListener("change", () => { dirty = true; }); });
    sheetSelect.addEventListener("change", () => {
      const chosen = Number(sheetSelect.value);
      if (dirty && !window.confirm("Changing worksheets clears this unsaved row selection and column mapping. Continue?")) { sheetSelect.value = String(sheet.index); return; }
      selected.clear(); headerInput.value = "1"; start = 1; mappingInputs.forEach((input) => { input.value = ""; }); setSheet(chosen); dirty = true;
    });
    headerInput.addEventListener("change", () => {
      const header = Number(headerInput.value);
      if (!Number.isInteger(header) || header < 1 || header >= sheet.rows) { problem("Choose a header before the worksheet's data rows."); return; }
      let removed = false;
      for (const row of selected.keys()) if (row <= header) { selected.delete(row); removed = true; }
      if (removed) problem("Rows now above the header were removed from the selected batch.");
      dirty = true; refreshMapping(); renderRows();
    });
    document.getElementById("xlsx-show-rows").addEventListener("click", () => { start = Number(startInput.value) || 1; renderRows(); });
    document.getElementById("xlsx-previous").addEventListener("click", () => { start = Math.max(1, start - 25); renderRows(); });
    document.getElementById("xlsx-next").addEventListener("click", () => { start = Math.min(sheet.rows, start + 25); renderRows(); });
    document.getElementById("xlsx-mapping-controls").disabled = form.dataset.canEdit !== "true";
    form.addEventListener("submit", (event) => {
      if (!selected.size || selected.size > 25) { event.preventDefault(); problem("Choose item kinds from one to 25 data rows before preparing a batch."); return; }
      document.getElementById("xlsx-plan").value = JSON.stringify({
        sheet_index: sheet.index, header_row: Number(headerInput.value),
        mapping: Object.fromEntries(mappingInputs.map((input) => [input.dataset.mapField, input.value === "" ? null : Number(input.value)])),
        selections: [...selected.entries()].sort((a, b) => a[0] - b[0]).map(([row, kinds]) => ({ row, kinds: ["defect", "opening", "service"].filter((kind) => kinds.has(kind)) })),
      });
      dirty = false;
    });
    window.addEventListener("beforeunload", (event) => { if (dirty) { event.preventDefault(); event.returnValue = ""; } });
  } catch { problem("The retained worksheet could not be loaded safely. Reload before mapping; no Draft changes have been saved."); }
})();
