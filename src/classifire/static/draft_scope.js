"use strict";

(() => {
  const form = document.getElementById("scope-editor");
  if (!form) return;
  const errorBox = document.getElementById("scope-client-error");
  const states = ["Unresolved", "Provisional", "Inferred", "Confirmed"];
  const kinds = ["defects", "openings", "services", "observations"];
  const titles = { defects: "Defect", openings: "Opening", services: "Service", observations: "Observation" };
  let payload;
  let dirty = document.getElementById("scope-download").hidden;

  function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = false;
    errorBox.scrollIntoView({ block: "nearest" });
  }

  function changed() {
    dirty = true;
    document.getElementById("scope-save-state").textContent = "Unsaved changes";
    document.getElementById("scope-download").hidden = true;
    document.getElementById("scope-download-hint").hidden = false;
    errorBox.hidden = true;
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function field(grid, item, name, title, options = {}) {
    const label = element("label", options.wide ? "scope-wide" : "", title);
    const input = element(options.multiline ? "textarea" : "input");
    input.id = `scope-${item.id}-${name}`;
    input.setAttribute("aria-label", title);
    label.htmlFor = input.id;
    input.value = item[name] ?? "";
    if (options.multiline) input.rows = 3;
    else input.type = "text";
    if (options.decimal) {
      input.inputMode = "decimal";
      input.pattern = "(?:0|[1-9][0-9]{0,8})(?:\\.[0-9]{1,6})?";
      input.maxLength = 16;
      input.placeholder = "Unknown";
      input.title = "Use up to 9 whole-number digits and 6 decimal places, or leave blank if unknown.";
    }
    if (options.maxLength) input.maxLength = options.maxLength;
    if (options.required) input.required = true;
    input.addEventListener("input", () => {
      item[name] = options.decimal && input.value === "" ? null : input.value;
      changed();
      if (name === "label") refreshRelations();
    });
    label.append(input);
    if (options.hint) label.append(element("span", "scope-hint", options.hint));
    grid.append(label);
    return input;
  }

  function selectField(grid, item, name, title, choices) {
    const label = element("label", "", title);
    const input = element("select");
    input.id = `scope-${item.id}-${name}`;
    input.setAttribute("aria-label", title);
    label.htmlFor = input.id;
    choices.forEach((choice) => input.append(new Option(choice, choice)));
    if (item[name] != null && !choices.includes(item[name])) {
      input.append(new Option(`Unrecognised: ${item[name]}`, item[name]));
    }
    input.value = item[name] ?? choices[0];
    input.addEventListener("change", () => { item[name] = input.value; changed(); });
    label.append(input);
    grid.append(label);
    return input;
  }

  function checkField(grid, item, name, title) {
    const label = element("label", "scope-check scope-wide");
    const input = element("input");
    input.type = "checkbox";
    input.id = `scope-${item.id}-${name}`;
    input.setAttribute("aria-label", title);
    label.htmlFor = input.id;
    input.checked = item[name] === true;
    input.addEventListener("change", () => { item[name] = input.checked; changed(); });
    label.append(input, document.createTextNode(title));
    grid.append(label);
  }

  function fillDefectSelect(select, item) {
    select.replaceChildren(new Option("Not linked / unknown", ""));
    payload.defects.forEach((defect, index) => select.append(new Option(defect.label || `Defect ${index + 1}`, defect.id)));
    if (item.defect_id && !payload.defects.some((defect) => defect.id === item.defect_id)) {
      select.append(new Option(`Unavailable defect (${item.defect_id})`, item.defect_id));
    }
    select.value = item.defect_id || "";
  }

  function fillOpeningChecks(container, item) {
    container.replaceChildren(element("legend", "", "Linked openings"));
    const choices = payload.openings.map((opening, index) => ({ id: opening.id, label: opening.label || `Opening ${index + 1}` }));
    item.opening_ids.forEach((id) => {
      if (!choices.some((opening) => opening.id === id)) choices.push({ id, label: `Unavailable opening (${id})` });
    });
    if (!choices.length) container.append(element("span", "scope-hint", "Add an opening above, then select it here. An unlinked service remains unresolved."));
    choices.forEach((opening) => {
      const label = element("label", "scope-check");
      const checkbox = element("input");
      checkbox.type = "checkbox";
      checkbox.id = `scope-${item.id}-opening-${opening.id}`;
      label.htmlFor = checkbox.id;
      checkbox.checked = item.opening_ids.includes(opening.id);
      checkbox.addEventListener("change", () => {
        item.opening_ids = item.opening_ids.filter((id) => id !== opening.id);
        if (checkbox.checked) item.opening_ids.push(opening.id);
        changed();
      });
      label.append(checkbox, document.createTextNode(opening.label));
      container.append(label);
    });
  }

  function refreshRelations() {
    payload.openings.forEach((item) => {
      const input = document.getElementById(`scope-${item.id}-defect_id`);
      if (input) fillDefectSelect(input, item);
    });
    payload.services.forEach((item) => {
      const container = document.getElementById(`scope-${item.id}-opening_ids`);
      if (container) fillOpeningChecks(container, item);
    });
  }

  function refreshEmptyStates() {
    kinds.forEach((kind) => { form.querySelector(`[data-empty="${kind}"]`).hidden = payload[kind].length > 0; });
  }

  function removeItem(kind, item, card) {
    if (kind === "defects" && payload.openings.some((opening) => opening.defect_id === item.id)) {
      showError("This defect still has linked openings. Change those opening links before removing it.");
      return;
    }
    if (kind === "openings" && payload.services.some((service) => service.opening_ids.includes(item.id))) {
      showError("This opening still has linked services. Deselect it from those services before removing it.");
      return;
    }
    payload[kind] = payload[kind].filter((entry) => entry.id !== item.id);
    card.remove();
    changed();
    refreshRelations();
    refreshEmptyStates();
    form.querySelector(`[data-add="${kind}"]`).focus();
  }

  function renderItem(kind, item) {
    const card = element("fieldset", "scope-item");
    card.append(element("legend", "", titles[kind]));
    const grid = element("div", "form-grid");
    card.append(grid);
    if (kind === "defects") {
      field(grid, item, "label", "Defect label", { maxLength: 200, required: true });
      field(grid, item, "description", "Description", { multiline: true, wide: true, maxLength: 4000 });
    }
    if (kind === "openings") {
      field(grid, item, "label", "Opening label", { maxLength: 200, required: true });
      const select = selectField(grid, item, "defect_id", "Related defect", []);
      fillDefectSelect(select, item);
      // An unlinked opening is represented as null, never a fabricated defect ID.
      select.addEventListener("change", () => { item.defect_id = select.value || null; });
      selectField(grid, item, "plane", "Plane", ["unknown", "wall", "floor", "soffit"]);
      field(grid, item, "substrate", "Substrate", { maxLength: 500, hint: "e.g. concrete, masonry or plasterboard. Leave blank if unknown." });
      field(grid, item, "width_mm", "Width (mm)", { decimal: true });
      field(grid, item, "height_mm", "Height (mm)", { decimal: true });
      selectField(grid, item, "state", "Evidence state", states);
      checkField(grid, item, "blank", "Blank opening: no services pass through it");
    }
    if (kind === "services") {
      field(grid, item, "label", "Service label", { maxLength: 200, required: true });
      field(grid, item, "service_type", "Service type", { maxLength: 500, hint: "e.g. cable bundle or metal pipe" });
      selectField(grid, item, "state", "Evidence state", states);
      field(grid, item, "quantity", "Quantity", { decimal: true, hint: "Enter only a quantity you can support. Blank means unknown." });
      selectField(grid, item, "unit", "Quantity unit", ["each", "m", "mm"]);
      const links = element("fieldset", "scope-relations scope-wide");
      links.id = `scope-${item.id}-opening_ids`;
      fillOpeningChecks(links, item);
      grid.append(links);
    }
    if (kind === "observations") {
      field(grid, item, "text", "Observation or unknown", { multiline: true, wide: true, maxLength: 4000, required: true });
      selectField(grid, item, "state", "Evidence state", states);
    }
    const footer = element("div", "scope-item-footer");
    footer.append(element("span", "scope-item-id", `Stable ID: ${item.id}`));
    const remove = element("button", "button button-small scope-remove", `Remove ${titles[kind].toLowerCase()}`);
    remove.type = "button";
    remove.addEventListener("click", () => removeItem(kind, item, card));
    footer.append(remove);
    card.append(footer);
    form.querySelector(`[data-items="${kind}"]`).append(card);
    return card;
  }

  function addItem(kind) {
    const id = crypto.randomUUID();
    const defaults = {
      defects: { id, label: "", description: "" },
      openings: { id, label: "", defect_id: null, plane: "unknown", substrate: "", width_mm: null, height_mm: null, blank: false, state: "Unresolved" },
      services: { id, label: "", opening_ids: [], service_type: "", quantity: null, unit: "each", state: "Unresolved" },
      observations: { id, text: "", state: "Unresolved" },
    };
    const item = defaults[kind];
    payload[kind].push(item);
    const card = renderItem(kind, item);
    changed();
    refreshRelations();
    refreshEmptyStates();
    card.querySelector("input, textarea, select").focus();
  }

  try {
    payload = JSON.parse(document.getElementById("scope-initial-payload").textContent);
    kinds.forEach((kind) => {
      if (!Array.isArray(payload[kind])) throw new Error("Invalid scope data");
      payload[kind].forEach((item) => renderItem(kind, item));
    });
    ["assumptions", "exclusions"].forEach((name) => {
      const input = document.getElementById(`scope-${name}`);
      input.value = payload[name].join("\n");
      input.addEventListener("input", () => {
        payload[name] = input.value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
        changed();
      });
    });
    form.querySelectorAll("[data-add]").forEach((button) => button.addEventListener("click", () => {
      try { addItem(button.dataset.add); }
      catch { showError("The editor could not add this item. Use a current browser over a secure connection or localhost, then reload before editing."); }
    }));
    refreshEmptyStates();
    document.getElementById("scope-edit-controls").disabled = form.dataset.canEdit !== "true";
    form.addEventListener("submit", () => {
      document.getElementById("scope-payload").value = JSON.stringify(payload);
      dirty = false;
    });
    window.addEventListener("beforeunload", (event) => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = "";
    });
  } catch {
    showError("The draft could not be loaded safely into the editor. Reload the page before making changes. Your saved revision is unchanged.");
  }
})();
