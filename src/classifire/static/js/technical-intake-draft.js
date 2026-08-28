(() => {
  "use strict";

  const form = document.querySelector("[data-technical-intake-draft-form]");
  if (!form) {
    return;
  }

  const fieldHost = form.querySelector("[data-intake-field-host]");
  const payloadInput = form.querySelector("[data-intake-payload-json]");
  const status = form.querySelector("[data-intake-status]");
  const addFieldButton = document.querySelector("[data-intake-add-field]");
  const fieldTemplate = document.querySelector("[data-intake-field-template]");
  const locatorTemplate = document.querySelector("[data-intake-locator-template]");
  const initialPayloadNode = document.querySelector("[data-intake-initial-payload]");
  const submitButton = form.querySelector('button[type="submit"]');
  const technicalDocumentId = form.dataset.technicalDocumentId || "";
  const sourceSha256 = form.dataset.sourceSha256 || "";
  const sourceSizeRaw = form.dataset.sourceSize || "";
  const sourceSize = Number.parseInt(sourceSizeRaw, 10);
  const previewAvailable = form.dataset.previewAvailable === "true";
  const uuid4Pattern = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
  const sha256Pattern = /^[0-9a-f]{64}$/;
  const verifiedPageEvent = "classifire:technical-preview-page-verified";
  const retainedSourceValue = Symbol("retainedSourceValue");
  let verifiedPage = null;

  const setStatus = (message) => {
    if (status) {
      status.textContent = message;
    }
  };

  const failInitialization = () => {
    if (submitButton) {
      submitButton.disabled = true;
    }
    if (addFieldButton) {
      addFieldButton.disabled = true;
    }
    setStatus(
      "This Draft editor could not confirm its saved payload and source binding. Reload before making changes.",
    );
  };

  if (
    !fieldHost
    || !payloadInput
    || !status
    || !addFieldButton
    || !fieldTemplate
    || !locatorTemplate
    || !initialPayloadNode
    || technicalDocumentId.length < 1
    || technicalDocumentId.length > 36
    || technicalDocumentId !== technicalDocumentId.trim()
    || /[\u0000-\u001f\u007f]/.test(technicalDocumentId)
    || !sha256Pattern.test(sourceSha256)
    || !/^[1-9][0-9]*$/.test(sourceSizeRaw)
    || !Number.isSafeInteger(sourceSize)
    || sourceSize > 1024 * 1024 * 1024
  ) {
    failInitialization();
    return;
  }

  const newRowId = () => {
    if (!globalThis.crypto || typeof globalThis.crypto.randomUUID !== "function") {
      throw new Error("DRAFT_UUID_UNAVAILABLE");
    }
    const rowId = globalThis.crypto.randomUUID().toLowerCase();
    if (!uuid4Pattern.test(rowId)) {
      throw new Error("DRAFT_UUID_INVALID");
    }
    return rowId;
  };

  const valueOrNull = (control) => {
    const value = control.value.trim();
    return value === "" ? null : value;
  };

  const normalizedTextareaValue = (value) => (
    value === null ? "" : value.replace(/\r\n?/g, "\n")
  );

  const rememberSourceValue = (control, value) => {
    control[retainedSourceValue] = value;
  };

  const sourceValueOrNull = (control) => {
    const retained = control[retainedSourceValue];
    if (
      (retained === null || typeof retained === "string")
      && normalizedTextareaValue(retained) === control.value
    ) {
      return retained;
    }
    return control.value.trim() === "" ? null : control.value;
  };

  const setValue = (root, selector, value) => {
    const control = root.querySelector(selector);
    control.value = value === null || value === undefined ? "" : String(value);
  };

  const updateFieldOrdinals = () => {
    Array.from(fieldHost.querySelectorAll("[data-intake-field]")).forEach(
      (field, index) => {
        field.querySelector("[data-intake-field-ordinal]").textContent = String(index + 1);
      },
    );
  };

  const updateVerifiedPageControls = (root = form) => {
    for (const button of root.querySelectorAll("[data-intake-use-verified-page]")) {
      const help = button.parentElement.querySelector("[data-intake-verified-page-help]");
      if (!previewAvailable) {
        button.hidden = true;
        button.disabled = true;
        help.textContent = "Enter the physical PDF page manually.";
      } else if (verifiedPage === null) {
        button.hidden = false;
        button.disabled = true;
        help.textContent = "This action unlocks only after a source-bound preview page is verified.";
      } else {
        button.hidden = false;
        button.disabled = false;
        help.textContent = `Verified preview page ${verifiedPage.pageNumber} is available.`;
      }
    }
  };

  const applyFactState = (field, {clearNormalized = false} = {}) => {
    const factState = field.querySelector("[data-intake-fact-state]").value;
    const normalized = field.querySelector("[data-intake-normalized-value]");
    const limitation = field.querySelector("[data-intake-limitation]");
    const unresolved = factState === "Unresolved";
    if (unresolved && clearNormalized) {
      normalized.value = "";
    }
    normalized.disabled = unresolved;
    limitation.required = unresolved;
  };

  const addLocator = (field, locator = null, link = null) => {
    const fragment = locatorTemplate.content.cloneNode(true);
    const editor = fragment.querySelector("[data-intake-locator]");
    const locatorRowId = locator ? locator.row_id : newRowId();
    const linkRowId = link ? link.row_id : newRowId();
    editor.querySelector("[data-intake-locator-row-id]").value = locatorRowId;
    editor.querySelector("[data-intake-link-row-id]").value = linkRowId;
    setValue(
      editor,
      "[data-intake-physical-page]",
      locator ? locator.physical_page : (verifiedPage ? verifiedPage.pageNumber : null),
    );
    for (const key of [
      "printed-page",
      "section",
      "clause",
      "table",
      "row",
      "column",
      "footnote",
      "figure",
      "drawing",
      "specimen",
      "option",
      "callout",
      "excerpt",
    ]) {
      const payloadKey = key.replace("-", "_");
      setValue(editor, `[data-intake-${key}]`, locator ? locator[payloadKey] : null);
    }
    setValue(
      editor,
      "[data-intake-evidence-role]",
      link ? link.evidence_role : "direct",
    );
    setValue(
      editor,
      "[data-intake-visual-verification]",
      locator ? locator.visual_verification : "required",
    );
    rememberSourceValue(
      editor.querySelector("[data-intake-excerpt]"),
      locator ? locator.excerpt : null,
    );
    for (const key of ["x0", "y0", "x1", "y1"]) {
      setValue(
        editor,
        `[data-intake-region-${key}]`,
        locator && locator.region ? locator.region[key] : null,
      );
    }
    editor.querySelector("[data-intake-use-verified-page]").addEventListener("click", () => {
      if (verifiedPage !== null) {
        editor.querySelector("[data-intake-physical-page]").value = String(
          verifiedPage.pageNumber,
        );
        setStatus(`Physical PDF page ${verifiedPage.pageNumber} copied from the verified preview.`);
      }
    });
    editor.querySelector("[data-intake-remove-locator]").addEventListener("click", () => {
      const locatorHost = field.querySelector("[data-intake-locator-host]");
      if (locatorHost.querySelectorAll("[data-intake-locator]").length <= 1) {
        setStatus("Every field must retain at least one source locator.");
        return;
      }
      editor.remove();
      setStatus("Source locator removed from the unsaved Draft.");
    });
    field.querySelector("[data-intake-locator-host]").append(fragment);
    updateVerifiedPageControls(field);
  };

  const addField = (fieldValue = null, locatorLinks = null) => {
    const fragment = fieldTemplate.content.cloneNode(true);
    const field = fragment.querySelector("[data-intake-field]");
    field.querySelector("[data-intake-field-row-id]").value = (
      fieldValue ? fieldValue.row_id : newRowId()
    );
    setValue(field, "[data-intake-field-key]", fieldValue ? fieldValue.field_key : "manufacturer");
    setValue(field, "[data-intake-fact-state]", fieldValue ? fieldValue.fact_state : "Provisional");
    setValue(field, "[data-intake-raw-value]", fieldValue ? fieldValue.raw_value : null);
    rememberSourceValue(
      field.querySelector("[data-intake-raw-value]"),
      fieldValue ? fieldValue.raw_value : null,
    );
    setValue(
      field,
      "[data-intake-normalized-value]",
      fieldValue ? fieldValue.normalized_value : null,
    );
    setValue(field, "[data-intake-unit]", fieldValue ? fieldValue.unit : null);
    setValue(field, "[data-intake-semantics]", fieldValue ? fieldValue.semantics : "exact");
    field.querySelector("[data-intake-material]").checked = fieldValue
      ? fieldValue.material
      : true;
    setValue(field, "[data-intake-limitation]", fieldValue ? fieldValue.limitation : null);
    field.querySelector("[data-intake-fact-state]").addEventListener("change", () => {
      applyFactState(field, {clearNormalized: true});
    });
    field.querySelector("[data-intake-add-locator]").addEventListener("click", () => {
      try {
        addLocator(field);
        setStatus("A new source locator was added to the unsaved Draft.");
      } catch (error) {
        setStatus("A stable locator ID could not be created. Reload before continuing.");
      }
    });
    field.querySelector("[data-intake-remove-field]").addEventListener("click", () => {
      field.remove();
      updateFieldOrdinals();
      setStatus("Field and its source links removed from the unsaved Draft.");
    });
    fieldHost.append(fragment);
    if (locatorLinks && locatorLinks.length > 0) {
      for (const entry of locatorLinks) {
        addLocator(field, entry.locator, entry.link);
      }
    } else {
      addLocator(field);
    }
    applyFactState(field);
    updateFieldOrdinals();
  };

  const boundedRegion = (editor) => {
    const controls = ["x0", "y0", "x1", "y1"].map((key) => (
      editor.querySelector(`[data-intake-region-${key}]`)
    ));
    const values = controls.map((control) => control.value.trim());
    if (values.every((value) => value === "")) {
      return null;
    }
    if (values.some((value) => !/^(?:0(?:\.\d{1,12})?|1(?:\.0{1,12})?)$/.test(value))) {
      throw new Error("Enter all four bounded region values between 0 and 1.");
    }
    const [x0, y0, x1, y1] = values.map(Number);
    if (!(x0 < x1 && y0 < y1)) {
      throw new Error("A bounded region requires x0 below x1 and y0 below y1.");
    }
    return {x0: values[0], y0: values[1], x1: values[2], y1: values[3]};
  };

  const canonicalJson = (value) => {
    const ordered = (item) => {
      if (Array.isArray(item)) {
        return item.map(ordered);
      }
      if (item !== null && typeof item === "object") {
        return Object.fromEntries(
          Object.keys(item).sort().map((key) => [key, ordered(item[key])]),
        );
      }
      return item;
    };
    return JSON.stringify(ordered(value));
  };

  const serializePayload = () => {
    const fields = [];
    const links = [];
    const locatorById = new Map();
    const rowKinds = new Map();
    const registerRow = (rowId, kind) => {
      if (!uuid4Pattern.test(rowId)) {
        throw new Error(`A ${kind} row has an invalid stable ID.`);
      }
      const existing = rowKinds.get(rowId);
      if (existing && (existing !== kind || kind !== "locator")) {
        throw new Error("Stable row IDs must be unique across fields, locators, and links.");
      }
      rowKinds.set(rowId, kind);
    };
    const fieldEditors = Array.from(fieldHost.querySelectorAll("[data-intake-field]"));
    fieldEditors.forEach((field, index) => {
      const rowId = field.querySelector("[data-intake-field-row-id]").value;
      registerRow(rowId, "field");
      const factState = field.querySelector("[data-intake-fact-state]").value;
      const rawValue = sourceValueOrNull(field.querySelector("[data-intake-raw-value]"));
      const normalizedValue = valueOrNull(
        field.querySelector("[data-intake-normalized-value]"),
      );
      const limitation = valueOrNull(field.querySelector("[data-intake-limitation]"));
      if (factState === "Unresolved") {
        if (normalizedValue !== null || limitation === null) {
          throw new Error("Unresolved facts require a limitation and cannot have a normalised value.");
        }
      } else if (rawValue === null && normalizedValue === null) {
        throw new Error("Each non-Unresolved fact needs a raw or normalised value.");
      }
      fields.push({
        row_id: rowId,
        ordinal: index + 1,
        field_key: field.querySelector("[data-intake-field-key]").value,
        raw_value: rawValue,
        normalized_value: normalizedValue,
        unit: valueOrNull(field.querySelector("[data-intake-unit]")),
        semantics: field.querySelector("[data-intake-semantics]").value,
        fact_state: factState,
        material: field.querySelector("[data-intake-material]").checked,
        limitation: limitation,
      });
      const locatorEditors = Array.from(
        field.querySelectorAll("[data-intake-locator]"),
      );
      if (locatorEditors.length === 0) {
        throw new Error("Every field requires at least one source locator.");
      }
      for (const editor of locatorEditors) {
        const locatorRowId = editor.querySelector("[data-intake-locator-row-id]").value;
        const linkRowId = editor.querySelector("[data-intake-link-row-id]").value;
        registerRow(locatorRowId, "locator");
        registerRow(linkRowId, "link");
        const pageValue = editor.querySelector("[data-intake-physical-page]").value.trim();
        if (!/^[1-9][0-9]*$/.test(pageValue)) {
          throw new Error("Every source locator requires a physical PDF page from 1 to 500.");
        }
        const physicalPage = Number.parseInt(pageValue, 10);
        if (!Number.isSafeInteger(physicalPage) || physicalPage > 500) {
          throw new Error("Every source locator requires a physical PDF page from 1 to 500.");
        }
        const locator = {
          row_id: locatorRowId,
          technical_document_id: technicalDocumentId,
          source_sha256: sourceSha256,
          source_size_bytes: sourceSize,
          physical_page: physicalPage,
          printed_page: valueOrNull(editor.querySelector("[data-intake-printed-page]")),
          section: valueOrNull(editor.querySelector("[data-intake-section]")),
          clause: valueOrNull(editor.querySelector("[data-intake-clause]")),
          table: valueOrNull(editor.querySelector("[data-intake-table]")),
          row: valueOrNull(editor.querySelector("[data-intake-row]")),
          column: valueOrNull(editor.querySelector("[data-intake-column]")),
          footnote: valueOrNull(editor.querySelector("[data-intake-footnote]")),
          figure: valueOrNull(editor.querySelector("[data-intake-figure]")),
          drawing: valueOrNull(editor.querySelector("[data-intake-drawing]")),
          specimen: valueOrNull(editor.querySelector("[data-intake-specimen]")),
          option: valueOrNull(editor.querySelector("[data-intake-option]")),
          callout: valueOrNull(editor.querySelector("[data-intake-callout]")),
          excerpt: sourceValueOrNull(editor.querySelector("[data-intake-excerpt]")),
          region: boundedRegion(editor),
          visual_verification: editor.querySelector(
            "[data-intake-visual-verification]",
          ).value,
        };
        const hasFinerLocator = [
          "printed_page",
          "section",
          "clause",
          "table",
          "row",
          "column",
          "footnote",
          "figure",
          "drawing",
          "specimen",
          "option",
          "callout",
          "excerpt",
          "region",
        ].some((key) => locator[key] !== null);
        if (!hasFinerLocator) {
          throw new Error("Each source locator needs a clause, table, row, figure, excerpt, region, or other finer reference.");
        }
        const existingLocator = locatorById.get(locatorRowId);
        if (existingLocator && canonicalJson(existingLocator) !== canonicalJson(locator)) {
          throw new Error("A shared source locator has conflicting edits.");
        }
        locatorById.set(locatorRowId, locator);
        links.push({
          row_id: linkRowId,
          field_row_id: rowId,
          locator_row_id: locatorRowId,
          evidence_role: editor.querySelector("[data-intake-evidence-role]").value,
        });
      }
    });
    return {
      schema: "technical-intake-payload-v1",
      fields,
      locators: Array.from(locatorById.values()).sort((left, right) => (
        left.row_id.localeCompare(right.row_id)
      )),
      links: links.sort((left, right) => left.row_id.localeCompare(right.row_id)),
    };
  };

  const loadInitialPayload = () => {
    const initial = JSON.parse(initialPayloadNode.textContent);
    if (
      !initial
      || initial.schema !== "technical-intake-payload-v1"
      || !Array.isArray(initial.fields)
      || !Array.isArray(initial.locators)
      || !Array.isArray(initial.links)
    ) {
      throw new Error("DRAFT_PAYLOAD_INVALID");
    }
    const locatorById = new Map(initial.locators.map((locator) => [locator.row_id, locator]));
    const linksByField = new Map();
    for (const link of initial.links) {
      const locator = locatorById.get(link.locator_row_id);
      if (!locator) {
        throw new Error("DRAFT_LINK_INVALID");
      }
      const entries = linksByField.get(link.field_row_id) || [];
      entries.push({link, locator});
      linksByField.set(link.field_row_id, entries);
    }
    for (const field of initial.fields) {
      const entries = linksByField.get(field.row_id);
      if (!entries || entries.length === 0) {
        throw new Error("DRAFT_EVIDENCE_INVALID");
      }
      addField(field, entries.sort((left, right) => (
        left.link.row_id.localeCompare(right.link.row_id)
      )));
    }
    payloadInput.value = canonicalJson(serializePayload());
  };

  document.addEventListener(verifiedPageEvent, (event) => {
    const detail = event.detail;
    if (
      !detail
      || detail.sourceSha256 !== sourceSha256
      || detail.sourceSize !== sourceSize
      || !Number.isSafeInteger(detail.pageNumber)
      || !Number.isSafeInteger(detail.pageCount)
      || detail.pageNumber < 1
      || detail.pageNumber > 500
      || detail.pageNumber > detail.pageCount
      || !sha256Pattern.test(detail.bindingSha256 || "")
      || !sha256Pattern.test(detail.pngSha256 || "")
    ) {
      return;
    }
    verifiedPage = Object.freeze({pageNumber: detail.pageNumber});
    updateVerifiedPageControls();
    setStatus(`Verified preview page ${detail.pageNumber} is ready for locator entry.`);
  });

  addFieldButton.addEventListener("click", () => {
    try {
      addField();
      setStatus("A new field and source locator were added to the unsaved Draft.");
    } catch (error) {
      setStatus("A stable field ID could not be created. Reload before continuing.");
    }
  });

  form.addEventListener("submit", (event) => {
    try {
      updateFieldOrdinals();
      payloadInput.value = canonicalJson(serializePayload());
      setStatus("Saving this authority-neutral Draft...");
    } catch (error) {
      event.preventDefault();
      payloadInput.value = "";
      setStatus(error instanceof Error ? error.message : "The Draft payload is invalid.");
    }
  });

  try {
    loadInitialPayload();
    updateVerifiedPageControls();
  } catch (error) {
    failInitialization();
  }
})();
