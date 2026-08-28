(() => {
  "use strict";

  const form = document.querySelector("#technical-batch-upload");
  if (!form) {
    return;
  }

  const fileInput = form.querySelector("#technical-files");
  const itemHost = form.querySelector("#technical-upload-items");
  const itemTemplate = document.querySelector("#technical-upload-item-template");
  const submitButton = form.querySelector("#technical-upload-submit");
  const newBatchButton = form.querySelector("#technical-upload-new-batch");
  const summary = form.querySelector("#technical-upload-summary");
  const csrfInput = form.querySelector('input[name="csrf_token"]');
  const batchCreateEndpoint = form.dataset.batchCreateEndpoint;
  const batchReadPrefix = form.dataset.batchReadPrefix;
  const batchLookupPrefix = form.dataset.batchLookupPrefix;
  const batchStorageKeyBase = (
    form.dataset.batchStorageKey || "classifire.technical.intake_batch"
  );
  const storageNamespace = form.dataset.storageNamespace;
  const batchStorageKey = batchStorageKeyBase + "." + storageNamespace;
  const pendingRequestStorageKey = batchStorageKey + ".pending_client_request";
  const maximumFiles = Number.parseInt(form.dataset.maxFiles || "20", 10);
  const requestTimeoutMilliseconds = Number.parseInt(
    form.dataset.requestTimeoutMs || "120000",
    10,
  );
  if (
    !fileInput
    || !itemHost
    || !itemTemplate
    || !submitButton
    || !newBatchButton
    || !summary
    || !csrfInput
    || !batchCreateEndpoint
    || !batchReadPrefix
    || !batchLookupPrefix
    || !storageNamespace
  ) {
    return;
  }

  const messages = {
    ARTIFACT_PROVENANCE_INVALID: "Choose how this exact file was obtained or transformed.",
    ARTIFACT_PROVENANCE_NOTE_REQUIRED: "Explain how this transformed file differs from the source artifact.",
    ARTIFACT_PROVENANCE_STATUS_INVALID: "Choose how this exact file was obtained or transformed.",
    AUTHENTICATION_REQUIRED: "Your session expired. Refresh and sign in before retrying.",
    CSRF_INVALID: "This upload page expired. Refresh before retrying.",
    DECLARED_SOURCE_ROLE_INVALID: "Choose the report's declared evidence role.",
    DOCUMENT_ID_ALREADY_EXISTS: "That Document ID already exists.",
    DOCUMENT_ID_INVALID: "Enter a valid Document ID.",
    DOCUMENT_TYPE_INVALID: "Choose a supported document type.",
    EVIDENCE_SCOPE_INVALID: "Choose the scope of evidence available in this report.",
    INTAKE_BATCH_ACKNOWLEDGEMENT_UNKNOWN: "The batch creation outcome is unknown.",
    INTAKE_BATCH_BODY_INVALID: "The batch manifest was not accepted.",
    INTAKE_BATCH_CONTENT_TYPE_INVALID: "The batch request format was not accepted.",
    INTAKE_BATCH_ITEM_IN_PROGRESS: "This report is already being processed.",
    INTAKE_BATCH_ITEM_NOT_RETRYABLE: "This report cannot be retried automatically.",
    INTAKE_BATCH_ITEM_REPLAY_MISMATCH: "The selected report no longer matches its batch record.",
    INTAKE_BATCH_MANIFEST_INVALID: "Check the report identity fields before creating the batch.",
    INTAKE_BATCH_MANIFEST_MISMATCH: "This browser request no longer matches the retained batch.",
    INTAKE_BATCH_NOT_FOUND: "This batch is unavailable for the signed-in account.",
    INTAKE_DATE_INVALID: "Check the declared report dates.",
    INTAKE_FIELD_INVALID: "Check the report identity fields.",
    INTAKE_STANDARDS_INVALID: "Check the comma or line separated standards.",
    MALWARE_DETECTED: "The report was rejected by malware screening.",
    MALWARE_SCAN_INPUT_INVALID: "The scanner could not safely read this report.",
    MALWARE_SCANNER_CONFIGURATION_INVALID: "The upload scanner is not configured correctly.",
    MALWARE_SCANNER_ERROR: "The upload scanner returned an error. Try again later.",
    MALWARE_SCANNER_REQUIRED: "Uploads are paused until malware screening is configured.",
    MALWARE_SCANNER_RESPONSE_MALFORMED: "The scanner returned an invalid result. Try again later.",
    MALWARE_SCANNER_TIMEOUT: "The scanner timed out. Try this report again.",
    MALWARE_SCANNER_UNAVAILABLE: "The scanner is unavailable. Try again later.",
    PENDING_REQUEST_STORAGE_REQUIRED: "Browser session storage is required before a batch can be created.",
    PERMISSION_DENIED: "Your account is not allowed to upload technical evidence.",
    RELATED_DOCUMENT_ID_INVALID: "Choose a valid existing source document.",
    RELATED_DOCUMENT_NOT_FOUND: "The selected source document no longer exists.",
    RELATIONSHIP_ALREADY_EXISTS: "That source relationship already exists.",
    RELATIONSHIP_CYCLE: "That relationship would create a source-history cycle.",
    RELATIONSHIP_EFFECTIVE_DATE_INVALID: "Check the relationship effective date.",
    RELATIONSHIP_FIELDS_INCOMPLETE: "Choose a relationship, source and reason together.",
    RELATIONSHIP_REASON_INVALID: "Enter a valid relationship reason.",
    RELATIONSHIP_SCOPE_INVALID: "Check the relationship scope.",
    RELATIONSHIP_SELF_REFERENCE: "A source document cannot be related to itself.",
    RELATIONSHIP_TYPE_INVALID: "Choose a supported source relationship.",
    SOURCE_CLASSIFICATION_INVALID: "The report classification is not allowed.",
    SOURCE_DOCUMENT_NOT_DRAFT: "Relationships can only be attached while the source is Draft.",
    SOURCE_METADATA_FIELD_INVALID: "Check the declared source registration fields.",
    SOURCE_ROLE_INVALID: "Choose the report's declared evidence role.",
    STORED_FILE_CONTENT_COLLISION: "A conflicting retained file already exists.",
    STORED_FILE_CONTEXT_CONFLICT: "These bytes already exist under incompatible evidence.",
    STORED_FILE_PERSISTENCE_CONFLICT: "The report could not be recorded safely.",
    STORED_FILE_STORAGE_FAILURE: "Secure evidence storage is unavailable.",
    SUMMARY_SOURCE_TARGET_INVALID: "A summary must point to retained full-source evidence.",
    TECHNICAL_INTAKE_AUDIT_FAILURE: "The rejection audit could not be recorded safely.",
    TECHNICAL_INTAKE_CONFLICT: "Another upload used the same identity.",
    TECHNICAL_UPLOAD_FORM_INVALID: "The upload request was invalid.",
    UPLOAD_CONTENT_SIGNATURE_INVALID: "The file contents do not match its extension.",
    UPLOAD_EXPECTED_CONTENT_MISMATCH: "The selected file no longer matches this batch item.",
    UPLOAD_FILE_EMPTY: "The selected report is empty.",
    UPLOAD_FILE_TYPE_UNSUPPORTED: "This file type is not supported.",
    UPLOAD_MULTIPLE_CLEANUP_FAILED: "Several secure cleanup steps failed.",
    UPLOAD_RESPONSE_MALFORMED: "The server response could not be verified.",
    UPLOAD_RETENTION_CLEANUP_FAILED: "Retained upload cleanup failed.",
    UPLOAD_SIZE_LIMIT_EXCEEDED: "This report exceeds the upload limit.",
    UPLOAD_STAGED_BYTES_CHANGED: "The staged report changed during validation.",
    UPLOAD_STREAM_INVALID: "The report could not be read safely.",
    UPLOAD_TEMP_CLEANUP_FAILED: "The secure upload area needs operator attention.",
  };

  const identityFieldNames = [
    "artifact_provenance_note", "artifact_provenance_status",
    "declared_source_role", "document_id", "document_type",
    "evidence_limitations", "evidence_scope", "expiry_date",
    "issuing_organisation", "jurisdiction", "manufacturer",
    "publication_date", "reference", "related_document_id",
    "relationship_effective_date", "relationship_reason",
    "relationship_scope", "relationship_type", "review_date",
    "revision", "sponsor_organisation", "standards", "title",
  ];
  const requiredIdentityFields = new Set([
    "artifact_provenance_status", "declared_source_role", "document_id",
    "document_type", "evidence_scope", "jurisdiction", "title",
  ]);
  const multilineIdentityFields = new Set([
    "artifact_provenance_note", "evidence_limitations", "relationship_scope",
  ]);
  const batchStatuses = new Set([
    "open", "in_progress", "needs_attention", "completed",
    "completed_with_rejections",
  ]);
  const itemStatuses = new Set([
    "pending", "processing", "accepted", "rejected", "needs_attention",
  ]);
  const retainedEvidenceAttentionCodes = new Set([
    "MALWARE_DETECTED", "STORED_FILE_CONTENT_COLLISION",
    "STORED_FILE_CONTEXT_CONFLICT", "UPLOAD_CONTENT_SIGNATURE_INVALID",
    "UPLOAD_STAGED_BYTES_CHANGED",
  ]);
  const refreshLockCodes = new Set([
    "AUTHENTICATION_REQUIRED", "CSRF_INVALID", "PERMISSION_DENIED",
    "PENDING_REQUEST_STORAGE_REQUIRED", "STORED_FILE_STORAGE_FAILURE",
    "TECHNICAL_INTAKE_AUDIT_FAILURE", "UPLOAD_MULTIPLE_CLEANUP_FAILED",
    "UPLOAD_RETENTION_CLEANUP_FAILED", "UPLOAD_TEMP_CLEANUP_FAILED",
  ]);
  const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
  const sha256Pattern = /^[0-9a-f]{64}$/;
  const batchResponseKeys = [
    "batch_id", "batch_schema", "client_request_id", "completed_at",
    "counts", "created_at", "expected_item_count", "idempotent_replay",
    "items", "manifest_sha256", "ok", "status", "status_url", "updated_at",
  ];
  const batchItemResponseKeys = [
    "attempt_count", "claim_expires_at", "client_item_id", "document_id", "expected_sha256",
    "filename", "item_id", "ordinal", "outcome_code", "receipt",
    "receipt_sha256", "registration", "registration_schema",
    "registration_sha256", "retained_file_sha256", "retryable",
    "size_bytes", "status", "technical_document_id",
  ];
  const uploadReceiptKeys = [
    "artifact_provenance_status", "batch_id", "declared_source_role",
    "document_id", "document_type", "evidence_scope",
    "exact_content_duplicate_document_ids", "extraction_status",
    "file_sha256", "id", "idempotent_replay", "item_id",
    "malware_scan_status", "ok", "receipt_sha256", "relationship",
    "status", "status_url",
  ];
  const uploadErrorKeys = ["code", "fatal", "ok", "retryable"];
  const acceptedBatchReceiptKeys = [
    "artifact_provenance_status", "batch_id", "declared_source_role",
    "document_id", "document_type", "evidence_scope",
    "exact_content_duplicate_document_ids", "extraction_status",
    "file_sha256", "http_status", "id", "item_id",
    "malware_scan_status", "ok", "relationship", "schema",
    "status", "status_url",
  ];
  const rejectedBatchReceiptKeys = [
    "batch_id", "code", "expected_sha256", "expected_size_bytes",
    "http_status", "item_id", "ok", "operator_attention",
    "retryable", "schema",
  ];

  let selected = [];
  let currentBatchId = null;
  let currentClientRequestId = null;
  let currentManifest = null;
  let batchRequiresRefresh = false;
  let batchRunning = false;
  let fileHashQueue = Promise.resolve();

  const field = (row, name) => row.querySelector('[data-field="' + name + '"]');
  const hasExactKeys = (value, expectedKeys) => (
    value !== null
    && typeof value === "object"
    && !Array.isArray(value)
    && Object.keys(value).sort().join("|") === [...expectedKeys].sort().join("|")
  );
  const isUuid = (value) => typeof value === "string" && uuidPattern.test(value);
  const isSha256 = (value) => typeof value === "string" && sha256Pattern.test(value);
  const isCanonicalFilename = (value) => (
    typeof value === "string"
    && value !== ""
    && [...value].length <= 500
    && value === value.trim()
    && !/[<>:"/\\|?*]/.test(value)
    && ![...value].some(
      (character) => character !== " " && /[\p{C}\p{Z}]/u.test(character),
    )
    && /^.+\.(pdf|docx|xlsx|xlsb)$/i.test(value)
  );
  const isValidUploadError = (value) => (
    hasExactKeys(value, uploadErrorKeys)
    && value.ok === false
    && typeof value.code === "string"
    && value.code !== ""
    && typeof value.retryable === "boolean"
    && typeof value.fatal === "boolean"
  );

  const applyRelationshipRequirements = (row) => {
    const selectedRelationship = field(row, "relationship_type").value.trim() !== "";
    field(row, "related_document_id").required = selectedRelationship;
    field(row, "relationship_reason").required = selectedRelationship;
  };
  const reportTypeDefaults = Object.freeze({
    fire_test_report: ["primary_test", "full_source"],
    fire_assessment: ["assessment", "full_source"],
    engineering_assessment: ["assessment", "full_source"],
    regulatory_information_report: ["regulatory_summary", "summary_only"],
    manufacturer_manual: ["manufacturer_information", "full_source"],
    technical_data_sheet: ["manufacturer_information", "full_source"],
  });
  const applyReportTypeDefaults = (row) => {
    const defaults = reportTypeDefaults[field(row, "document_type").value];
    if (defaults) {
      field(row, "declared_source_role").value = defaults[0];
      field(row, "evidence_scope").value = defaults[1];
    } else {
      field(row, "declared_source_role").value = "";
      field(row, "evidence_scope").value = "";
    }
  };
  const lockIdentity = (item, locked) => {
    for (const name of identityFieldNames) {
      field(item.row, name).disabled = locked;
    }
  };
  const standardsSnapshot = (value) => {
    const standards = value
      .split(/[\r\n,]+/)
      .map((item) => item.trim())
      .filter(Boolean);
    return standards.length ? Object.freeze(standards) : null;
  };
  const snapshotIdentity = (item) => {
    const identity = {};
    for (const name of identityFieldNames) {
      const input = field(item.row, name);
      const value = (
        multilineIdentityFields.has(name)
          ? input.value.replace(/\r\n?/g, "\n")
          : input.value
      ).trim();
      input.value = value;
      if (name === "standards") {
        identity[name] = standardsSnapshot(value);
      } else if (requiredIdentityFields.has(name)) {
        identity[name] = value;
      } else {
        identity[name] = value || null;
      }
    }
    return Object.freeze(identity);
  };
  const populateIdentity = (item, identity) => {
    for (const name of identityFieldNames) {
      const value = identity[name];
      field(item.row, name).value = Array.isArray(value)
        ? value.join("\n")
        : (value || "");
    }
    applyRelationshipRequirements(item.row);
  };

  const reportStem = (filename) => {
    const lastDot = filename.lastIndexOf(".");
    return (lastDot > 0 ? filename.slice(0, lastDot) : filename).trim()
      || "Technical report";
  };
  const documentSlug = (filename, index) => {
    const stem = reportStem(filename)
      .normalize("NFKD")
      .replace(/[^A-Za-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .toUpperCase()
      .slice(0, 150) || "REPORT";
    const day = new Date().toISOString().slice(0, 10).replaceAll("-", "");
    return "DOC-" + day + "-" + stem + "-" + (index + 1);
  };
  const formatBytes = (size) => {
    if (size < 1024) {
      return size + " B";
    }
    if (size < 1024 * 1024) {
      return (size / 1024).toFixed(1) + " KB";
    }
    return (size / (1024 * 1024)).toFixed(1) + " MB";
  };
  const setStatus = (item, text) => {
    item.status.textContent = text;
  };

  const randomUuid = () => {
    if (!globalThis.crypto || typeof globalThis.crypto.randomUUID !== "function") {
      throw new Error("WEB_CRYPTO_UNAVAILABLE");
    }
    return globalThis.crypto.randomUUID();
  };
  const asciiJsonString = (value) => (
    JSON.stringify(value).replace(
      /[\u007f-\uffff]/g,
      (character) => "\\u"
        + character.charCodeAt(0).toString(16).padStart(4, "0"),
    )
  );
  const canonicalJson = (value) => {
    if (value === null) {
      return "null";
    }
    if (typeof value === "string") {
      return asciiJsonString(value);
    }
    if (typeof value === "boolean") {
      return value ? "true" : "false";
    }
    if (typeof value === "number" && Number.isFinite(value)) {
      return JSON.stringify(value);
    }
    if (Array.isArray(value)) {
      return "[" + value.map((item) => canonicalJson(item)).join(",") + "]";
    }
    if (typeof value === "object") {
      return "{" + Object.keys(value).sort().map(
        (key) => asciiJsonString(key) + ":" + canonicalJson(value[key]),
      ).join(",") + "}";
    }
    throw new Error("CANONICAL_JSON_INVALID");
  };
  const digestBytes = async (bytes) => {
    if (
      !globalThis.crypto
      || !globalThis.crypto.subtle
      || typeof globalThis.crypto.subtle.digest !== "function"
    ) {
      throw new Error("WEB_CRYPTO_UNAVAILABLE");
    }
    const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
    return Array.from(
      new Uint8Array(digest),
      (byte) => byte.toString(16).padStart(2, "0"),
    ).join("");
  };
  const sha256File = async (file) => digestBytes(await file.arrayBuffer());
  const sha256CanonicalJson = async (value) => (
    digestBytes(new TextEncoder().encode(canonicalJson(value)))
  );
  const hashFileSequentially = (file) => {
    const task = fileHashQueue.then(() => sha256File(file));
    fileHashQueue = task.catch(() => undefined);
    return task;
  };

  const createItem = (file, index) => {
    const fragment = itemTemplate.content.cloneNode(true);
    const row = fragment.querySelector("[data-upload-item]");
    const item = {
      clientItemId: null,
      expectedSha256: null,
      file,
      filename: file ? file.name : "",
      identity: null,
      itemId: null,
      name: fragment.querySelector("[data-file-name]"),
      retryControl: fragment.querySelector("[data-retry-file-control]"),
      retryInput: fragment.querySelector("[data-retry-file]"),
      row,
      serverItem: null,
      sizeBytes: file ? file.size : 0,
      state: "ready",
      status: fragment.querySelector("[data-upload-status]"),
    };
    if (file) {
      item.name.textContent = file.name + " | " + formatBytes(file.size);
      field(row, "document_id").value = documentSlug(file.name, index);
    }
    field(row, "document_type").addEventListener("change", () => {
      applyReportTypeDefaults(row);
    });
    field(row, "relationship_type").addEventListener("change", () => {
      applyRelationshipRequirements(row);
    });
    item.retryInput.addEventListener("change", () => {
      void selectRetryFile(item);
    });
    applyReportTypeDefaults(row);
    applyRelationshipRequirements(row);
    return item;
  };
  const immutableFileMatches = (item, file) => (
    file && file.name === item.filename && file.size === item.sizeBytes
  );
  const retryableItem = (item) => (
    item.serverItem
    && item.serverItem.retryable === true
    && ["pending", "processing", "rejected"].includes(item.serverItem.status)
  );
  const pendingManifestItem = (item) => (
    currentBatchId === null
    && currentManifest !== null
    && item.itemId === null
  );
  const fileSelectableItem = (item) => (
    retryableItem(item) || pendingManifestItem(item)
  );
  const renderPendingItem = (item) => {
    item.state = "unconfirmed";
    item.retryControl.hidden = false;
    item.retryInput.disabled = batchRunning;
    setStatus(
      item,
      item.file
        ? "Batch creation is unconfirmed. Exact file retained for safe replay."
        : "Batch creation is unconfirmed. Reselect the exact file for safe replay.",
    );
  };
  const renderItemOutcome = (item) => {
    const serverItem = item.serverItem;
    if (!serverItem) {
      return;
    }
    const receipt = isSha256(serverItem.receipt_sha256)
      ? " Receipt " + serverItem.receipt_sha256.slice(0, 12) + "..."
      : "";
    if (serverItem.status === "accepted") {
      setStatus(item, "Accepted as immutable Draft evidence." + receipt);
    } else if (serverItem.status === "processing") {
      setStatus(
        item,
        serverItem.retryable
          ? "The earlier server claim expired. Reselect the exact file to retry."
          : "Processing on the server. Refresh will reconcile this item.",
      );
    } else if (serverItem.status === "needs_attention") {
      setStatus(
        item,
        "Operator attention required"
          + (serverItem.outcome_code ? " (" + serverItem.outcome_code + ")" : "")
          + "." + receipt,
      );
    } else if (serverItem.status === "rejected") {
      const explanation = messages[serverItem.outcome_code]
        || "The report was rejected.";
      setStatus(
        item,
        explanation
          + (serverItem.outcome_code ? " (" + serverItem.outcome_code + ")" : "")
          + (serverItem.retryable ? " Reselect the exact file to retry." : "")
          + receipt,
      );
    } else if (item.file) {
      setStatus(item, "Exact file ready for secure upload");
    } else {
      setStatus(item, "Pending. Reselect the exact file to continue.");
    }
    item.retryControl.hidden = !retryableItem(item);
    item.retryInput.disabled = batchRunning || !retryableItem(item);
  };

  const updateSummary = (prefix = "") => {
    if (!selected.length) {
      summary.textContent = prefix || "No reports selected";
      return;
    }
    const count = (state) => selected.filter((item) => item.state === state).length;
    const unresolved = selected.length
      - count("accepted") - count("rejected") - count("needs_attention");
    const parts = [
      count("accepted") + " accepted",
      count("rejected") + " rejected",
      count("needs_attention") + " needs attention",
      unresolved + " unresolved",
    ];
    const identity = currentBatchId ? "Batch " + currentBatchId + ". " : "";
    summary.textContent = identity + (prefix ? prefix + " " : "") + parts.join(" | ");
  };
  const syncControls = () => {
    const hasReadyRetry = selected.some((item) => retryableItem(item) && item.file);
    const awaitingBatchCreation = currentBatchId === null && currentManifest !== null;
    const pendingManifestReady = (
      awaitingBatchCreation
      && selected.length > 0
      && selected.every((item) => item.file)
    );
    fileInput.disabled = (
      batchRunning
      || batchRequiresRefresh
      || currentBatchId !== null
      || awaitingBatchCreation
    );
    submitButton.disabled = (
      batchRunning
      || batchRequiresRefresh
      || (
        currentBatchId === null
          ? (awaitingBatchCreation ? !pendingManifestReady : selected.length === 0)
          : !hasReadyRetry
      )
    );
    newBatchButton.hidden = (
      currentBatchId === null
      && currentClientRequestId === null
      && currentManifest === null
    );
    newBatchButton.disabled = batchRunning;
    for (const item of selected) {
      item.retryInput.disabled = batchRunning || !fileSelectableItem(item);
    }
  };
  const renderSelection = () => {
    if (batchRunning || batchRequiresRefresh || currentBatchId !== null) {
      syncControls();
      return;
    }
    itemHost.replaceChildren();
    const files = Array.from(fileInput.files || []);
    if (files.length > maximumFiles) {
      selected = [];
      summary.textContent = "Select no more than " + maximumFiles
        + " reports in one batch.";
      syncControls();
      return;
    }
    if (files.some((file) => !isCanonicalFilename(file.name))) {
      selected = [];
      summary.textContent = (
        "Each report needs a plain PDF, DOCX, XLSX, or XLSB filename "
        + "without path characters or surrounding spaces."
      );
      syncControls();
      return;
    }
    selected = files.map((file, index) => createItem(file, index));
    for (const item of selected) {
      itemHost.appendChild(item.row);
    }
    summary.textContent = selected.length
      ? selected.length + " report" + (selected.length === 1 ? "" : "s")
        + " ready"
      : "No reports selected";
    syncControls();
  };

  const getResponseCode = (response, payload, fallback) => {
    if (payload && typeof payload.code === "string") {
      return payload.code;
    }
    if (payload && typeof payload.detail === "string") {
      return payload.detail;
    }
    if (response && response.status === 401) {
      return "AUTHENTICATION_REQUIRED";
    }
    if (response && response.status === 403) {
      return "PERMISSION_DENIED";
    }
    return fallback;
  };
  const requestJson = async (url, options) => {
    const controller = new AbortController();
    const timeout = globalThis.setTimeout(
      () => controller.abort(),
      requestTimeoutMilliseconds,
    );
    try {
      const response = await fetch(url, {
        ...options,
        credentials: "same-origin",
        signal: controller.signal,
      });
      let payload;
      try {
        payload = await response.json();
      } catch {
        const error = new Error("UPLOAD_RESPONSE_MALFORMED");
        error.response = response;
        throw error;
      }
      return {payload, response};
    } catch (error) {
      if (controller.signal.aborted) {
        throw new Error("REQUEST_TIMEOUT");
      }
      throw error;
    } finally {
      globalThis.clearTimeout(timeout);
    }
  };

  const persistBatchId = (batchId) => {
    try {
      globalThis.sessionStorage.setItem(batchStorageKey, batchId);
      globalThis.sessionStorage.removeItem(pendingRequestStorageKey);
    } catch {
      // URL persistence remains available when browser storage is disabled.
    }
    const url = new URL(globalThis.location.href);
    url.searchParams.set("intake_batch", batchId);
    globalThis.history.replaceState(null, "", url);
  };
  const clearPersistedBatch = () => {
    try {
      globalThis.sessionStorage.removeItem(batchStorageKey);
      globalThis.sessionStorage.removeItem(pendingRequestStorageKey);
    } catch {
      // URL cleanup remains available when browser storage is disabled.
    }
    const url = new URL(globalThis.location.href);
    url.searchParams.delete("intake_batch");
    globalThis.history.replaceState(null, "", url);
  };
  const persistPendingRequestId = (clientRequestId) => {
    if (!isUuid(clientRequestId)) {
      throw new Error("UPLOAD_RESPONSE_MALFORMED");
    }
    try {
      globalThis.sessionStorage.setItem(
        pendingRequestStorageKey,
        clientRequestId,
      );
      return (
        globalThis.sessionStorage.getItem(pendingRequestStorageKey)
        === clientRequestId
      );
    } catch {
      return false;
    }
  };
  const clearPendingRequestId = () => {
    try {
      globalThis.sessionStorage.removeItem(pendingRequestStorageKey);
    } catch {
      // No durable pending value is available when storage is disabled.
    }
  };
  const requestedBatchId = () => {
    const fromUrl = new URL(globalThis.location.href)
      .searchParams.get("intake_batch");
    if (isUuid(fromUrl)) {
      return fromUrl;
    }
    try {
      const fromStorage = globalThis.sessionStorage.getItem(batchStorageKey);
      return isUuid(fromStorage) ? fromStorage : null;
    } catch {
      return null;
    }
  };

  const requestedPendingRequestId = () => {
    try {
      const clientRequestId = globalThis.sessionStorage.getItem(
        pendingRequestStorageKey,
      );
      return isUuid(clientRequestId) ? clientRequestId : null;
    } catch {
      return null;
    }
  };

  const isValidRegistration = (registration) => (
    hasExactKeys(registration, identityFieldNames)
    && identityFieldNames.every((name) => {
      const value = registration[name];
      if (name === "standards") {
        return value === null || (
          Array.isArray(value)
          && value.length > 0
          && value.every((item) => typeof item === "string")
        );
      }
      if (requiredIdentityFields.has(name)) {
        return typeof value === "string" && value !== "";
      }
      return value === null || typeof value === "string";
    })
  );
  const validateReceiptHash = async (receipt, receiptSha256) => {
    if (receipt === null) {
      return receiptSha256 === null;
    }
    return isSha256(receiptSha256)
      && await sha256CanonicalJson(receipt) === receiptSha256;
  };
  const validateBatchItemReceipt = async (item, batchId) => {
    if (!await validateReceiptHash(item.receipt, item.receipt_sha256)) {
      return false;
    }
    const receipt = item.receipt;
    if (item.status === "pending") {
      return (
        item.outcome_code === null
        && item.retryable === true
        && item.technical_document_id === null
        && item.retained_file_sha256 === null
        && receipt === null
      );
    }
    if (item.status === "accepted") {
      return (
        item.attempt_count > 0
        && item.outcome_code === "ACCEPTED"
        && item.retryable === false
        && isUuid(item.technical_document_id)
        && item.retained_file_sha256 === item.expected_sha256
        && hasExactKeys(receipt, acceptedBatchReceiptKeys)
        && receipt.schema === "technical-intake-item-receipt-v1"
        && receipt.ok === true
        && receipt.http_status === 201
        && receipt.batch_id === batchId
        && receipt.item_id === item.item_id
        && receipt.id === item.technical_document_id
        && receipt.document_id === item.document_id
        && receipt.document_type === item.registration.document_type
        && receipt.declared_source_role
          === item.registration.declared_source_role
        && receipt.artifact_provenance_status
          === item.registration.artifact_provenance_status
        && receipt.evidence_scope === item.registration.evidence_scope
        && receipt.status === "draft"
        && receipt.file_sha256 === item.expected_sha256
        && receipt.malware_scan_status === "clean"
        && receipt.extraction_status === "awaiting_safe_extraction"
        && receipt.status_url === batchReadPrefix + batchId
        && isValidRelationshipReceipt(
          receipt.relationship,
          item.registration,
        )
        && isValidDuplicateReceipt(
          receipt.exact_content_duplicate_document_ids,
          item.document_id,
        )
      );
    }
    if (item.status === "processing" && receipt === null) {
      return (
        item.attempt_count > 0
        && item.outcome_code === null
        && item.technical_document_id === null
        && item.retained_file_sha256 === null
      );
    }
    const hasNoAcceptedEvidence = (
      item.technical_document_id === null
      && item.retained_file_sha256 === null
    );
    const hasRetainedAcceptedEvidence = (
      item.status === "needs_attention"
      && retainedEvidenceAttentionCodes.has(item.outcome_code)
      && isUuid(item.technical_document_id)
      && item.retained_file_sha256 === item.expected_sha256
    );
    if (
      !["processing", "rejected", "needs_attention"].includes(item.status)
      || item.attempt_count < 1
      || typeof item.outcome_code !== "string"
      || item.outcome_code === ""
      || (!hasNoAcceptedEvidence && !hasRetainedAcceptedEvidence)
      || !hasExactKeys(receipt, rejectedBatchReceiptKeys)
      || receipt.schema !== "technical-intake-item-receipt-v1"
      || receipt.ok !== false
      || receipt.batch_id !== batchId
      || receipt.item_id !== item.item_id
      || receipt.code !== item.outcome_code
      || receipt.expected_sha256 !== item.expected_sha256
      || receipt.expected_size_bytes !== item.size_bytes
      || !Number.isInteger(receipt.http_status)
      || receipt.http_status < 400
      || receipt.http_status > 599
      || typeof receipt.retryable !== "boolean"
      || typeof receipt.operator_attention !== "boolean"
    ) {
      return false;
    }
    if (item.status === "processing") {
      return (
        receipt.retryable === true
        && receipt.operator_attention === false
      );
    }
    if (item.status === "needs_attention") {
      return (
        item.retryable === false
        && receipt.retryable === false
        && receipt.operator_attention === true
      );
    }
    return (
      receipt.operator_attention === false
      && item.retryable === receipt.retryable
    );
  };

  const validateBatchPayload = async (
    payload,
    {batchId = null, manifest = null, readResponse = false} = {},
  ) => {
    if (
      !hasExactKeys(payload, batchResponseKeys)
      || payload.ok !== true
      || !isUuid(payload.batch_id)
      || (batchId !== null && payload.batch_id !== batchId)
      || payload.batch_schema !== "technical-intake-batch-v1"
      || !isUuid(payload.client_request_id)
      || !isSha256(payload.manifest_sha256)
      || !batchStatuses.has(payload.status)
      || !Number.isInteger(payload.expected_item_count)
      || payload.expected_item_count < 1
      || payload.expected_item_count > maximumFiles
      || !Array.isArray(payload.items)
      || payload.items.length !== payload.expected_item_count
      || typeof payload.idempotent_replay !== "boolean"
      || (readResponse && payload.idempotent_replay !== false)
      || payload.status_url !== batchReadPrefix + payload.batch_id
      || Number.isNaN(Date.parse(payload.created_at))
      || Number.isNaN(Date.parse(payload.updated_at))
      || (
        payload.completed_at !== null
        && Number.isNaN(Date.parse(payload.completed_at))
      )
      || !hasExactKeys(
        payload.counts,
        ["accepted", "needs_attention", "pending", "processing", "rejected"],
      )
    ) {
      throw new Error("UPLOAD_RESPONSE_MALFORMED");
    }
    const expectedByClientId = manifest
      ? new Map(manifest.items.map((item) => [item.client_item_id, item]))
      : null;
    if (manifest && payload.client_request_id !== manifest.client_request_id) {
      throw new Error("UPLOAD_RESPONSE_MALFORMED");
    }
    const serverIds = new Set();
    const clientIds = new Set();
    const ordinals = new Set();
    for (const item of payload.items) {
      if (
        !hasExactKeys(item, batchItemResponseKeys)
        || !isUuid(item.item_id)
        || !isUuid(item.client_item_id)
        || serverIds.has(item.item_id)
        || clientIds.has(item.client_item_id)
        || !Number.isInteger(item.ordinal)
        || item.ordinal < 1
        || item.ordinal > payload.items.length
        || ordinals.has(item.ordinal)
        || !isCanonicalFilename(item.filename)
        || !Number.isInteger(item.size_bytes)
        || item.size_bytes < 1
        || !isSha256(item.expected_sha256)
        || typeof item.document_id !== "string"
        || item.document_id === ""
        || item.registration_schema !== "technical-source-registration-v1"
        || !isValidRegistration(item.registration)
        || item.registration.document_id !== item.document_id
        || !isSha256(item.registration_sha256)
        || await sha256CanonicalJson(item.registration)
          !== item.registration_sha256
        || !itemStatuses.has(item.status)
        || !Number.isInteger(item.attempt_count)
        || item.attempt_count < 0
        || (item.outcome_code !== null && typeof item.outcome_code !== "string")
        || (
          item.status === "processing"
            ? (
              typeof item.claim_expires_at !== "string"
              || Number.isNaN(Date.parse(item.claim_expires_at))
            )
            : item.claim_expires_at !== null
        )
        || typeof item.retryable !== "boolean"
        || (
          item.technical_document_id !== null
          && !isUuid(item.technical_document_id)
        )
        || (
          item.retained_file_sha256 !== null
          && !isSha256(item.retained_file_sha256)
        )
        || !await validateBatchItemReceipt(item, payload.batch_id)
      ) {
        throw new Error("UPLOAD_RESPONSE_MALFORMED");
      }
      serverIds.add(item.item_id);
      clientIds.add(item.client_item_id);
      ordinals.add(item.ordinal);
      if (expectedByClientId) {
        const expected = expectedByClientId.get(item.client_item_id);
        if (
          !expected
          || item.ordinal !== expected.ordinal
          || item.filename !== expected.filename
          || item.size_bytes !== expected.size_bytes
          || item.expected_sha256 !== expected.expected_sha256
          || canonicalJson(item.registration)
            !== canonicalJson(expected.registration)
        ) {
          throw new Error("UPLOAD_RESPONSE_MALFORMED");
        }
      }
    }
    const reconstructedManifest = {
      batch_schema: payload.batch_schema,
      client_request_id: payload.client_request_id,
      items: payload.items.map((item) => ({
        client_item_id: item.client_item_id,
        expected_sha256: item.expected_sha256,
        filename: item.filename,
        ordinal: item.ordinal,
        registration: item.registration,
        registration_sha256: item.registration_sha256,
        size_bytes: item.size_bytes,
      })),
    };
    if (
      await sha256CanonicalJson(reconstructedManifest)
      !== payload.manifest_sha256
    ) {
      throw new Error("UPLOAD_RESPONSE_MALFORMED");
    }
    const countTotal = Object.values(payload.counts).reduce((total, value) => {
      if (!Number.isInteger(value) || value < 0) {
        throw new Error("UPLOAD_RESPONSE_MALFORMED");
      }
      return total + value;
    }, 0);
    if (countTotal !== payload.items.length) {
      throw new Error("UPLOAD_RESPONSE_MALFORMED");
    }
    const actualCounts = Object.fromEntries(
      [...itemStatuses].map((state) => [
        state,
        payload.items.filter((item) => item.status === state).length,
      ]),
    );
    if (
      [...itemStatuses].some(
        (state) => payload.counts[state] !== actualCounts[state],
      )
    ) {
      throw new Error("UPLOAD_RESPONSE_MALFORMED");
    }
    let derivedStatus = "open";
    if (actualCounts.needs_attention > 0) {
      derivedStatus = "needs_attention";
    } else if (actualCounts.accepted === payload.items.length) {
      derivedStatus = "completed";
    } else if (
      actualCounts.accepted + actualCounts.rejected === payload.items.length
    ) {
      derivedStatus = "completed_with_rejections";
    } else if (actualCounts.pending !== payload.items.length) {
      derivedStatus = "in_progress";
    }
    const terminal = new Set([
      "completed",
      "completed_with_rejections",
    ]).has(derivedStatus);
    if (
      payload.status !== derivedStatus
      || terminal !== (payload.completed_at !== null)
    ) {
      throw new Error("UPLOAD_RESPONSE_MALFORMED");
    }
    return payload;
  };

  const isValidRelationshipReceipt = (relationship, identity) => {
    if (identity.relationship_type === null) {
      return relationship === null;
    }
    return (
      hasExactKeys(relationship, ["relationship_type", "related_document_id"])
      && relationship.relationship_type === identity.relationship_type
      && relationship.related_document_id === identity.related_document_id
    );
  };
  const isValidDuplicateReceipt = (documentIds, currentDocumentId) => {
    if (!Array.isArray(documentIds)) {
      return false;
    }
    const unique = new Set();
    for (const documentId of documentIds) {
      if (
        typeof documentId !== "string"
        || documentId.length === 0
        || documentId.length > 200
        || documentId !== documentId.trim()
        || documentId === currentDocumentId
        || unique.has(documentId)
      ) {
        return false;
      }
      unique.add(documentId);
    }
    return true;
  };
  const isValidSuccessReceipt = async (
    response,
    httpStatus,
    correlationId,
    item,
  ) => {
    if (
      !hasExactKeys(response, uploadReceiptKeys)
      || response.ok !== true
      || ![200, 201].includes(httpStatus)
      || !isUuid(response.id)
      || response.document_id !== item.identity.document_id
      || response.document_type !== item.identity.document_type
      || response.declared_source_role !== item.identity.declared_source_role
      || response.artifact_provenance_status
        !== item.identity.artifact_provenance_status
      || response.evidence_scope !== item.identity.evidence_scope
      || response.batch_id !== correlationId
      || response.item_id !== item.itemId
      || response.idempotent_replay !== (httpStatus === 200)
      || response.status !== "draft"
      || response.malware_scan_status !== "clean"
      || response.extraction_status !== "awaiting_safe_extraction"
      || response.file_sha256 !== item.expectedSha256
      || response.status_url !== batchReadPrefix + correlationId
      || !isSha256(response.receipt_sha256)
      || !isValidRelationshipReceipt(response.relationship, item.identity)
      || !isValidDuplicateReceipt(
        response.exact_content_duplicate_document_ids,
        item.identity.document_id,
      )
    ) {
      return false;
    }
    const receipt = {
      artifact_provenance_status: response.artifact_provenance_status,
      batch_id: response.batch_id,
      declared_source_role: response.declared_source_role,
      document_id: response.document_id,
      document_type: response.document_type,
      evidence_scope: response.evidence_scope,
      exact_content_duplicate_document_ids:
        response.exact_content_duplicate_document_ids,
      extraction_status: response.extraction_status,
      file_sha256: response.file_sha256,
      http_status: 201,
      id: response.id,
      item_id: response.item_id,
      malware_scan_status: response.malware_scan_status,
      ok: true,
      relationship: response.relationship,
      schema: "technical-intake-item-receipt-v1",
      status: response.status,
      status_url: response.status_url,
    };
    return await sha256CanonicalJson(receipt) === response.receipt_sha256;
  };

  const fetchBatch = async (batchId, manifest = null) => {
    const {payload, response} = await requestJson(
      batchReadPrefix + batchId,
      {
        cache: "no-store",
        headers: {Accept: "application/json"},
        method: "GET",
      },
    );
    if (!response.ok) {
      throw new Error(
        getResponseCode(response, payload, "INTAKE_BATCH_NOT_FOUND"),
      );
    }
    return validateBatchPayload(
      payload,
      {batchId, manifest, readResponse: true},
    );
  };
  const fetchBatchByClientRequest = async (
    clientRequestId,
    manifest = null,
  ) => {
    const {payload, response} = await requestJson(
      batchLookupPrefix + encodeURIComponent(clientRequestId),
      {
        cache: "no-store",
        headers: {Accept: "application/json"},
        method: "GET",
      },
    );
    if (response.status === 404) {
      return null;
    }
    if (!response.ok) {
      throw new Error(
        getResponseCode(response, payload, "INTAKE_BATCH_ACKNOWLEDGEMENT_UNKNOWN"),
      );
    }
    const batch = await validateBatchPayload(
      payload,
      {manifest, readResponse: true},
    );
    if (batch.client_request_id !== clientRequestId) {
      throw new Error("UPLOAD_RESPONSE_MALFORMED");
    }
    return batch;
  };
  const reconcilePendingRequest = async (
    clientRequestId,
    manifest = null,
  ) => {
    let priorError = null;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const batch = await fetchBatchByClientRequest(
          clientRequestId,
          manifest,
        );
        if (batch !== null) {
          return batch;
        }
        priorError = new Error("INTAKE_BATCH_NOT_FOUND");
      } catch (error) {
        priorError = error;
        if (error && refreshLockCodes.has(error.message)) {
          throw error;
        }
      }
    }
    if (priorError && priorError.message !== "INTAKE_BATCH_NOT_FOUND") {
      throw priorError;
    }
    return null;
  };
  const candidateBatchId = (payload, manifest) => (
    payload
    && isUuid(payload.batch_id)
    && payload.client_request_id === manifest.client_request_id
      ? payload.batch_id
      : null
  );
  const createServerBatch = async (manifest) => {
    const body = JSON.stringify({
      client_request_id: manifest.client_request_id,
      items: manifest.items,
    });
    let priorError = null;
    let ambiguousAttempt = false;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const {payload, response} = await requestJson(
          batchCreateEndpoint,
          {
            body,
            cache: "no-store",
            headers: {
              Accept: "application/json",
              "Content-Type": "application/json",
              "X-CSRF-Token": csrfInput.value,
            },
            method: "POST",
          },
        );
        if (!response.ok) {
          const rejection = new Error(
            getResponseCode(
              response,
              payload,
              "INTAKE_BATCH_ACKNOWLEDGEMENT_UNKNOWN",
            ),
          );
          rejection.definite = response.status >= 400 && response.status < 500;
          throw rejection;
        }
        try {
          return await validateBatchPayload(payload, {manifest});
        } catch (error) {
          const candidate = candidateBatchId(payload, manifest);
          if (candidate) {
            return await fetchBatch(candidate, manifest);
          }
          throw error;
        }
      } catch (error) {
        priorError = error;
        const isDefinite = error && error.definite === true;
        const requiresRefresh = (
          error && refreshLockCodes.has(error.message)
        );
        if (isDefinite || requiresRefresh) {
          if (!ambiguousAttempt) {
            throw error;
          }
        } else {
          ambiguousAttempt = true;
        }
      }
    }
    if (ambiguousAttempt) {
      try {
        const reconciled = await reconcilePendingRequest(
          manifest.client_request_id,
          manifest,
        );
        if (reconciled !== null) {
          return reconciled;
        }
      } catch {
        // A failed lookup cannot make an earlier ambiguous POST definite.
      }
      const uncertain = new Error("INTAKE_BATCH_ACKNOWLEDGEMENT_UNKNOWN");
      uncertain.ambiguous = true;
      throw uncertain;
    }
    throw priorError || new Error("INTAKE_BATCH_ACKNOWLEDGEMENT_UNKNOWN");
  };
  const createPersistedServerBatch = async (manifest) => {
    if (!persistPendingRequestId(manifest.client_request_id)) {
      const error = new Error("PENDING_REQUEST_STORAGE_REQUIRED");
      error.storageRequired = true;
      throw error;
    }
    return createServerBatch(manifest);
  };

  const applyBatchState = (batch) => {
    const existingByClientId = new Map(
      selected
        .filter((item) => item.clientItemId)
        .map((item) => [item.clientItemId, item]),
    );
    const next = [];
    for (const serverItem of batch.items) {
      const item = existingByClientId.get(serverItem.client_item_id)
        || createItem(null, serverItem.ordinal - 1);
      item.clientItemId = serverItem.client_item_id;
      item.expectedSha256 = serverItem.expected_sha256;
      item.filename = serverItem.filename;
      item.identity = Object.freeze({
        ...serverItem.registration,
        standards: Array.isArray(serverItem.registration.standards)
          ? Object.freeze([...serverItem.registration.standards])
          : null,
      });
      item.itemId = serverItem.item_id;
      item.serverItem = serverItem;
      item.sizeBytes = serverItem.size_bytes;
      item.state = serverItem.status;
      if (
        serverItem.status === "processing"
        || !immutableFileMatches(item, item.file)
      ) {
        item.file = null;
      }
      item.name.textContent = (
        serverItem.ordinal + ". " + serverItem.filename
        + " | " + formatBytes(serverItem.size_bytes)
        + " | SHA-256 " + serverItem.expected_sha256.slice(0, 12) + "..."
      );
      populateIdentity(item, item.identity);
      lockIdentity(item, true);
      renderItemOutcome(item);
      next.push(item);
    }
    selected = next;
    currentBatchId = batch.batch_id;
    currentClientRequestId = batch.client_request_id;
    itemHost.replaceChildren(...selected.map((item) => item.row));
    updateSummary("Server status: " + batch.status + ".");
    syncControls();
  };

  const applyPendingManifest = (manifest) => {
    const existingByClientId = new Map(
      selected
        .filter((item) => item.clientItemId)
        .map((item) => [item.clientItemId, item]),
    );
    const next = [];
    for (const manifestItem of manifest.items) {
      const item = existingByClientId.get(manifestItem.client_item_id)
        || createItem(null, manifestItem.ordinal - 1);
      item.clientItemId = manifestItem.client_item_id;
      item.expectedSha256 = manifestItem.expected_sha256;
      item.filename = manifestItem.filename;
      item.identity = manifestItem.registration;
      item.itemId = null;
      item.serverItem = null;
      item.sizeBytes = manifestItem.size_bytes;
      if (!immutableFileMatches(item, item.file)) {
        item.file = null;
      }
      item.name.textContent = (
        manifestItem.ordinal + ". " + manifestItem.filename
        + " | " + formatBytes(manifestItem.size_bytes)
        + " | SHA-256 " + manifestItem.expected_sha256.slice(0, 12) + "..."
      );
      populateIdentity(item, item.identity);
      lockIdentity(item, true);
      renderPendingItem(item);
      next.push(item);
    }
    selected = next;
    currentBatchId = null;
    currentClientRequestId = manifest.client_request_id;
    currentManifest = manifest;
    itemHost.replaceChildren(...selected.map((item) => item.row));
    updateSummary("Server batch creation remains unconfirmed.");
    syncControls();
  };

  const prepareManifest = async () => {
    const items = [];
    currentClientRequestId = currentClientRequestId || randomUuid();
    for (let index = 0; index < selected.length; index += 1) {
      const item = selected[index];
      item.identity = snapshotIdentity(item);
      if (!isCanonicalFilename(item.file.name)) {
        throw new Error("INTAKE_BATCH_MANIFEST_INVALID");
      }
      lockIdentity(item, true);
      item.state = "hashing";
      setStatus(item, "Hashing locally before batch creation");
      updateSummary();
      item.expectedSha256 = await hashFileSequentially(item.file);
      item.clientItemId = item.clientItemId || randomUuid();
      item.filename = item.file.name;
      item.sizeBytes = item.file.size;
      items.push({
        client_item_id: item.clientItemId,
        expected_sha256: item.expectedSha256,
        filename: item.filename,
        ordinal: index + 1,
        registration: item.identity,
        size_bytes: item.sizeBytes,
      });
      item.state = "ready";
      setStatus(item, "Hashed and ready for immutable batch creation");
    }
    return Object.freeze({
      client_request_id: currentClientRequestId,
      items: Object.freeze(items),
    });
  };
  const appendRegistration = (payload, identity) => {
    for (const name of identityFieldNames) {
      const value = identity[name];
      payload.append(
        name,
        Array.isArray(value) ? value.join("\n") : (value || ""),
      );
    }
  };

  const uploadOne = (item, correlationId) => new Promise((resolve) => {
    const payload = new FormData();
    payload.append("file", item.file, item.file.name);
    appendRegistration(payload, item.identity);
    payload.append("batch_id", correlationId);
    payload.append("item_id", item.itemId);

    let settled = false;
    const finish = (outcome) => {
      if (!settled) {
        settled = true;
        resolve(outcome);
      }
    };
    try {
      const request = new XMLHttpRequest();
      request.open("POST", form.dataset.endpoint);
      request.responseType = "json";
      request.timeout = requestTimeoutMilliseconds;
      request.setRequestHeader("Accept", "application/json");
      request.setRequestHeader("X-CSRF-Token", csrfInput.value);
      request.setRequestHeader(
        "X-Classifire-Intake-Batch-ID",
        correlationId,
      );
      request.setRequestHeader(
        "X-Classifire-Intake-Item-ID",
        item.itemId,
      );
      request.upload.addEventListener("progress", (event) => {
        if (event.lengthComputable) {
          const percent = Math.min(
            99,
            Math.round((event.loaded / event.total) * 100),
          );
          setStatus(item, "Uploading | " + percent + "%");
        } else {
          setStatus(item, "Uploading");
        }
      });
      request.upload.addEventListener("load", () => {
        setStatus(item, "Screening and retaining");
      });
      request.addEventListener("load", () => {
        void (async () => {
          const response = (
            request.response !== null
            && typeof request.response === "object"
            && !Array.isArray(request.response)
          ) ? request.response : null;
          const successful = request.status >= 200 && request.status < 300;
          if (
            successful
            && await isValidSuccessReceipt(
              response,
              request.status,
              correlationId,
              item,
            )
          ) {
            item.state = "accepted";
            const duplicateIds = response.exact_content_duplicate_document_ids;
            const duplicateNotice = duplicateIds.length
              ? " Exact content already exists as: "
                + duplicateIds.join(", ") + "."
              : "";
            setStatus(
              item,
              "Accepted as immutable Draft evidence." + duplicateNotice,
            );
            finish({code: null, halt: false, reconcile: true});
            return;
          }
          if (successful) {
            item.state = "unconfirmed";
            setStatus(
              item,
              messages.UPLOAD_RESPONSE_MALFORMED
                + " (UPLOAD_RESPONSE_MALFORMED)",
            );
            finish({
              code: "UPLOAD_RESPONSE_MALFORMED",
              halt: false,
              reconcile: true,
            });
            return;
          }
          const code = getResponseCode(request, response, "UPLOAD_FAILED");
          const validError = isValidUploadError(response);
          item.state = "unconfirmed";
          setStatus(
            item,
            (messages[code] || "Upload failed.") + " (" + code + ")",
          );
          finish({
            code,
            halt: validError ? response.fatal : true,
            reconcile: true,
          });
        })().catch(() => {
          item.state = "unconfirmed";
          setStatus(item, messages.UPLOAD_RESPONSE_MALFORMED);
          finish({
            code: "UPLOAD_RESPONSE_MALFORMED",
            halt: false,
            reconcile: true,
          });
        });
      });
      const uncertain = (code, text) => {
        item.state = "unconfirmed";
        setStatus(item, text);
        finish({code, halt: false, reconcile: true});
      };
      request.addEventListener("error", () => {
        uncertain(
          "NETWORK_ERROR",
          "Network error. Reconciling with the retained batch.",
        );
      });
      request.addEventListener("abort", () => {
        uncertain(
          "REQUEST_ABORTED",
          "Upload interrupted. Reconciling with the retained batch.",
        );
      });
      request.addEventListener("timeout", () => {
        uncertain(
          "REQUEST_TIMEOUT",
          "Upload timed out. Reconciling with the retained batch.",
        );
      });
      request.send(payload);
    } catch {
      item.state = "unconfirmed";
      setStatus(
        item,
        "The browser could not finish this upload. Reconciling the batch.",
      );
      finish({
        code: "CLIENT_UPLOAD_ERROR",
        halt: false,
        reconcile: true,
      });
    }
  });

  const runQueue = async (queue, correlationId) => {
    let cursor = 0;
    let halted = null;
    let reconciliationRequired = false;
    const worker = async () => {
      while (!halted && cursor < queue.length) {
        const item = queue[cursor];
        cursor += 1;
        item.state = "uploading";
        setStatus(item, "Preparing secure upload");
        const outcome = await uploadOne(item, correlationId);
        reconciliationRequired = reconciliationRequired || outcome.reconcile;
        if (outcome.halt && !halted) {
          halted = outcome;
        }
        updateSummary();
      }
    };
    const workerCount = Math.min(2, queue.length);
    await Promise.all(
      Array.from({length: workerCount}, () => worker()),
    );
    return {halted, reconciliationRequired};
  };
  const preserveQueueRefreshLock = (outcome) => {
    if (
      outcome
      && outcome.halted
      && refreshLockCodes.has(outcome.halted.code)
    ) {
      batchRequiresRefresh = true;
      return true;
    }
    return false;
  };

  const selectRetryFile = async (item) => {
    if (batchRunning || !fileSelectableItem(item)) {
      return;
    }
    const files = Array.from(item.retryInput.files || []);
    if (files.length !== 1) {
      item.file = null;
      setStatus(item, "Choose exactly one file for this batch row.");
      syncControls();
      return;
    }
    const file = files[0];
    if (!immutableFileMatches(item, file)) {
      item.file = null;
      item.retryInput.value = "";
      setStatus(
        item,
        "The selected file name or size does not match the batch manifest.",
      );
      syncControls();
      return;
    }
    batchRunning = true;
    syncControls();
    setStatus(item, "Verifying the selected file SHA-256");
    try {
      const digest = await hashFileSequentially(file);
      if (digest !== item.expectedSha256) {
        item.file = null;
        item.retryInput.value = "";
        setStatus(
          item,
          "The selected file hash does not match the batch manifest.",
        );
      } else {
        item.file = file;
        setStatus(item, "Exact file verified and ready to retry.");
      }
    } catch {
      item.file = null;
      setStatus(item, "The browser could not hash this file safely.");
    } finally {
      batchRunning = false;
      syncControls();
    }
  };

  const restoreBatch = async (batchId) => {
    batchRunning = true;
    fileInput.disabled = true;
    submitButton.disabled = true;
    summary.textContent = "Restoring retained batch status...";
    try {
      const batch = await fetchBatch(batchId);
      persistBatchId(batch.batch_id);
      applyBatchState(batch);
      batchRequiresRefresh = false;
    } catch (error) {
      if (error && error.message === "INTAKE_BATCH_NOT_FOUND") {
        batchRequiresRefresh = false;
        currentBatchId = null;
        clearPersistedBatch();
        summary.textContent = messages.INTAKE_BATCH_NOT_FOUND;
      } else {
        currentBatchId = batchId;
        batchRequiresRefresh = true;
        summary.textContent = (
          "The retained batch could not be confirmed. Refresh to try again."
        );
      }
    } finally {
      batchRunning = false;
      syncControls();
    }
  };
  const restorePendingRequest = async (clientRequestId) => {
    currentBatchId = null;
    currentClientRequestId = clientRequestId;
    currentManifest = null;
    batchRequiresRefresh = false;
    batchRunning = true;
    selected = [];
    itemHost.replaceChildren();
    fileInput.disabled = true;
    submitButton.disabled = true;
    summary.textContent = "Checking whether the server created this batch...";
    try {
      const batch = await reconcilePendingRequest(clientRequestId);
      if (batch !== null) {
        persistBatchId(batch.batch_id);
        applyBatchState(batch);
        batchRequiresRefresh = false;
      } else {
        batchRequiresRefresh = true;
        summary.textContent = (
          "Batch creation remains unconfirmed for request "
            + clientRequestId
            + ". Refresh to reconcile, or choose Start another batch only "
            + "if you intend to abandon this request."
        );
      }
    } catch {
      batchRequiresRefresh = true;
      summary.textContent = (
        "Batch creation remains unconfirmed for request "
          + clientRequestId
          + ". Refresh to reconcile, or choose Start another batch only "
          + "if you intend to abandon this request."
      );
    } finally {
      batchRunning = false;
      syncControls();
    }
  };
  const reconcileCurrentBatch = async () => {
    const batch = await fetchBatch(currentBatchId, currentManifest);
    batchRequiresRefresh = false;
    persistBatchId(batch.batch_id);
    applyBatchState(batch);
    return batch;
  };

  fileInput.addEventListener("change", renderSelection);
  newBatchButton.addEventListener("click", () => {
    if (batchRunning) {
      return;
    }
    clearPersistedBatch();
    currentBatchId = null;
    currentClientRequestId = null;
    currentManifest = null;
    batchRequiresRefresh = false;
    selected = [];
    fileInput.value = "";
    itemHost.replaceChildren();
    renderSelection();
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (batchRunning || batchRequiresRefresh) {
      return;
    }
    if (
      currentBatchId === null
      && currentManifest === null
      && !form.reportValidity()
    ) {
      return;
    }
    let fatalQueueRefreshLockCode = null;
    batchRunning = true;
    syncControls();
    try {
      if (currentBatchId === null) {
        if (!selected.length || selected.some((item) => !item.file)) {
          throw new Error("UPLOAD_STREAM_INVALID");
        }
        if (currentManifest === null) {
          currentManifest = await prepareManifest();
        }
        updateSummary("Creating immutable server batch.");
        const created = await createPersistedServerBatch(currentManifest);
        currentBatchId = created.batch_id;
        persistBatchId(created.batch_id);
        applyBatchState(created);
      }
      const queue = selected.filter(
        (item) => retryableItem(item) && item.file,
      );
      if (!queue.length) {
        await reconcileCurrentBatch();
        return;
      }
      for (const item of queue) {
        item.state = "queued";
        setStatus(item, "Waiting for secure upload");
      }
      updateSummary();
      const outcome = await runQueue(queue, currentBatchId);
      if (preserveQueueRefreshLock(outcome)) {
        fatalQueueRefreshLockCode = outcome.halted.code;
      }
      if (outcome.halted) {
        const explanation = messages[outcome.halted.code]
          || "A shared authentication or integrity error paused this batch.";
        updateSummary("Batch paused. " + explanation);
      }
      if (outcome.reconciliationRequired) {
        await reconcileCurrentBatch();
      }
      if (fatalQueueRefreshLockCode !== null) {
        const explanation = messages[outcome.halted.code]
          || "A shared authentication or integrity error paused this batch.";
        updateSummary(
          "Batch paused. " + explanation
            + " Refresh before any further upload.",
        );
      }
    } catch (error) {
      const code = error && typeof error.message === "string"
        ? error.message
        : "CLIENT_UPLOAD_ERROR";
      if (error && error.storageRequired === true) {
        batchRequiresRefresh = true;
        summary.textContent = (
          messages.PENDING_REQUEST_STORAGE_REQUIRED
          + " No batch was created. Enable session storage or refresh "
          + "before trying again."
        );
      } else if (currentBatchId !== null) {
        try {
          await reconcileCurrentBatch();
        } catch {
          batchRequiresRefresh = true;
          updateSummary(
            "The latest server outcome could not be confirmed. "
              + "Refresh to restore this batch.",
          );
        }
      } else {
        if (error && error.definite === true) {
          clearPendingRequestId();
          currentClientRequestId = null;
          currentManifest = null;
          for (const item of selected) {
            lockIdentity(item, false);
            if (item.state === "hashing") {
              item.state = "ready";
            }
          }
          summary.textContent = messages[code]
            || "The server rejected the batch manifest. Check the fields.";
        } else if (currentManifest !== null) {
          persistPendingRequestId(currentManifest.client_request_id);
          applyPendingManifest(currentManifest);
          summary.textContent = (
            "Batch creation is unconfirmed. The same request ID and manifest "
              + "will be reused; do not start a duplicate batch."
          );
        } else {
          summary.textContent = messages[code]
            || "The browser could not prepare a safe batch manifest.";
        }
      }
    } finally {
      batchRunning = false;
      if (fatalQueueRefreshLockCode !== null) {
        batchRequiresRefresh = true;
      }
      for (const item of selected) {
        if (item.serverItem) {
          lockIdentity(item, true);
          renderItemOutcome(item);
        }
      }
      if (fatalQueueRefreshLockCode !== null) {
        const explanation = messages[fatalQueueRefreshLockCode]
          || "A shared authentication or integrity error paused this batch.";
        updateSummary(
          "Batch paused. " + explanation
            + " Refresh before any further upload.",
        );
      }
      syncControls();
    }
  });

  const batchToRestore = requestedBatchId();
  if (batchToRestore) {
    void restoreBatch(batchToRestore);
  } else {
    const pendingRequestToRestore = requestedPendingRequestId();
    if (pendingRequestToRestore) {
      void restorePendingRequest(pendingRequestToRestore);
    } else {
      renderSelection();
    }
  }
})();
