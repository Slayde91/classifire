"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const productionScript = process.argv[2];
assert.ok(productionScript, "expected the technical-upload.js path");

class ListenerTarget {
  constructor() {
    this.listeners = new Map();
  }

  addEventListener(name, callback) {
    this.listeners.set(name, callback);
  }

  dispatch(name, event = {}) {
    const callback = this.listeners.get(name);
    assert.ok(callback, `missing ${name} listener`);
    return callback(event);
  }
}

const control = () => Object.assign(new ListenerTarget(), {
  disabled: false,
  files: [],
  hidden: false,
  value: "",
});

const fileInput = control();
const itemHost = {
  appendChild() {},
  replaceChildren() {},
};
const submitButton = control();
const newBatchButton = control();
const summary = {textContent: ""};
const csrfInput = {value: "csrf-token"};
const form = Object.assign(new ListenerTarget(), {
  dataset: {
    batchCreateEndpoint: "/api/v1/technical/upload-batches",
    batchLookupPrefix: "/api/v1/technical/upload-batches/by-client-request/",
    batchReadPrefix: "/api/v1/technical/upload-batches/",
    batchStorageKey: "classifire.technical.intake_batch",
    endpoint: "/technical/upload",
    maxFiles: "20",
    requestTimeoutMs: "120000",
    storageNamespace: "queue-test-user",
  },
  querySelector(selector) {
    return new Map([
      ["#technical-files", fileInput],
      ["#technical-upload-items", itemHost],
      ["#technical-upload-submit", submitButton],
      ["#technical-upload-new-batch", newBatchButton],
      ["#technical-upload-summary", summary],
      ['input[name="csrf_token"]', csrfInput],
    ]).get(selector) || null;
  },
  reportValidity() {
    return true;
  },
});

globalThis.document = {
  querySelector(selector) {
    if (selector === "#technical-batch-upload") {
      return form;
    }
    if (selector === "#technical-upload-item-template") {
      return {content: {cloneNode: () => assert.fail("unexpected item render")}};
    }
    return null;
  },
};
globalThis.history = {replaceState() {}};
globalThis.location = {href: "https://classifire.example.test/technical"};
globalThis.sessionStorage = {
  getItem() {
    return null;
  },
  removeItem() {},
  setItem() {},
};

class FakeFormData {
  constructor() {
    this.values = new Map();
  }

  append(name, value) {
    this.values.set(name, value);
  }
}

const requests = [];
class FakeXMLHttpRequest extends ListenerTarget {
  constructor() {
    super();
    this.headers = new Map();
    this.response = null;
    this.status = 0;
    this.upload = new ListenerTarget();
    requests.push(this);
  }

  open() {}

  setRequestHeader(name, value) {
    this.headers.set(name, value);
  }

  send(body) {
    this.body = body;
  }

  respond(status, response) {
    this.status = status;
    this.response = response;
    this.dispatch("load");
  }
}

globalThis.FormData = FakeFormData;
globalThis.XMLHttpRequest = FakeXMLHttpRequest;
let fetchCalls = 0;
globalThis.fetch = async () => {
  fetchCalls += 1;
  throw new Error("unexpected network request");
};
let reconcileCalls = 0;
globalThis.__reconcileCurrentBatchHarness = async () => {
  reconcileCalls += 1;
  if (reconcileCalls === 1) {
    throw new Error("first reconciliation failed");
  }
};

let source = fs.readFileSync(productionScript, "utf8");
source = source.replaceAll("\r\n", "\n");
const productionReconcile = [
  "  const reconcileCurrentBatch = async () => {",
  "    const batch = await fetchBatch(currentBatchId, currentManifest);",
  "    batchRequiresRefresh = false;",
  "    persistBatchId(batch.batch_id);",
  "    applyBatchState(batch);",
  "    return batch;",
  "  };",
].join("\n");
const harnessReconcile = [
  "  const reconcileCurrentBatch = async () => {",
  "    await globalThis.__reconcileCurrentBatchHarness();",
  "    batchRequiresRefresh = false;",
  "  };",
].join("\n");
assert.ok(source.includes(productionReconcile), "reconciliation function changed");
source = source.replace(productionReconcile, harnessReconcile);
const closingMarker = source.lastIndexOf("})();");
assert.notEqual(closingMarker, -1, "technical upload IIFE marker missing");
source = source.slice(0, closingMarker)
  + "globalThis.__technicalUploadQueueHarness = "
  + "{applyReportTypeDefaults, createPersistedServerBatch, preserveQueueRefreshLock, "
  + "isCanonicalFilename, runQueue, syncControls, "
  + "setSubmitState(items, batchId) {"
  + " selected = items; currentBatchId = batchId;"
  + " currentManifest = null; batchRequiresRefresh = false; },"
  + "requiresRefresh() { return batchRequiresRefresh; }};\n"
  + source.slice(closingMarker);
vm.runInThisContext(source, {filename: productionScript});

const makeItem = (number) => ({
  file: {name: `report-${number}.pdf`},
  identity: new Proxy({}, {get: () => null}),
  itemId: `item-${number}`,
  state: "queued",
  status: {textContent: ""},
});
const makeSubmitItem = (number) => {
  const item = makeItem(number);
  const fields = new Map();
  item.file = {name: `report-${number}.pdf`, size: 100 + number};
  item.retryControl = {hidden: false};
  item.retryInput = control();
  item.row = {
    querySelector(selector) {
      if (!fields.has(selector)) {
        fields.set(selector, control());
      }
      return fields.get(selector);
    },
  };
  item.serverItem = {
    outcome_code: null,
    receipt_sha256: null,
    retryable: true,
    status: "pending",
  };
  return item;
};

const waitForTurn = () => new Promise((resolve) => setImmediate(resolve));

(async () => {
  const reportTypeItem = makeSubmitItem(99);
  const reportType = reportTypeItem.row.querySelector(
    '[data-field="document_type"]',
  );
  const sourceRole = reportTypeItem.row.querySelector(
    '[data-field="declared_source_role"]',
  );
  const evidenceScope = reportTypeItem.row.querySelector(
    '[data-field="evidence_scope"]',
  );
  reportType.value = "fire_test_report";
  globalThis.__technicalUploadQueueHarness.applyReportTypeDefaults(
    reportTypeItem.row,
  );
  assert.equal(sourceRole.value, "primary_test");
  assert.equal(evidenceScope.value, "full_source");
  reportType.value = "fire_engineering_report_performance_solution";
  globalThis.__technicalUploadQueueHarness.applyReportTypeDefaults(
    reportTypeItem.row,
  );
  assert.equal(sourceRole.value, "", "ambiguous type must clear a prior role");
  assert.equal(
    evidenceScope.value,
    "",
    "ambiguous type must clear a prior evidence scope",
  );

  const items = [makeItem(1), makeItem(2), makeItem(3)];
  const queueResult = globalThis.__technicalUploadQueueHarness.runQueue(
    items,
    "batch-id",
  );

  assert.equal(requests.length, 2, "the two-worker queue should start two uploads");
  assert.deepEqual(
    requests.map((request) => request.body.values.get("item_id")),
    ["item-1", "item-2"],
  );
  assert.deepEqual(
    requests.map((request) => request.headers.get(
      "X-Classifire-Intake-Batch-ID",
    )),
    ["batch-id", "batch-id"],
  );
  assert.deepEqual(
    requests.map((request) => request.headers.get(
      "X-Classifire-Intake-Item-ID",
    )),
    ["item-1", "item-2"],
  );

  requests[0].respond(503, {
    code: "STORED_FILE_STORAGE_FAILURE",
    fatal: true,
    ok: false,
    retryable: true,
  });
  await waitForTurn();
  await waitForTurn();

  assert.equal(
    requests.length,
    2,
    "no new upload may start after a valid fatal response",
  );
  assert.equal(items[2].state, "queued");

  requests[1].respond(422, {
    code: "MALWARE_DETECTED",
    fatal: false,
    ok: false,
    retryable: false,
  });
  const outcome = await queueResult;

  assert.equal(requests.length, 2);
  assert.equal(outcome.halted.code, "STORED_FILE_STORAGE_FAILURE");
  assert.equal(outcome.halted.halt, true);
  assert.equal(outcome.reconciliationRequired, true);
  assert.equal(
    globalThis.__technicalUploadQueueHarness.preserveQueueRefreshLock(outcome),
    true,
  );
  globalThis.__technicalUploadQueueHarness.syncControls();
  assert.equal(fileInput.disabled, true);
  assert.equal(submitButton.disabled, true);
  assert.equal(items[2].state, "queued");

  await assert.rejects(
    globalThis.__technicalUploadQueueHarness.createPersistedServerBatch({
      client_request_id: "11111111-1111-4111-8111-111111111111",
      items: [],
    }),
    {message: "PENDING_REQUEST_STORAGE_REQUIRED"},
  );
  assert.equal(fetchCalls, 0, "no batch POST may occur without durable request ID storage");

  assert.equal(
    globalThis.__technicalUploadQueueHarness.isCanonicalFilename(".pdf"),
    false,
  );
  assert.equal(
    globalThis.__technicalUploadQueueHarness.isCanonicalFilename(
      "🔥".repeat(496) + ".pdf",
    ),
    true,
  );
  assert.equal(
    globalThis.__technicalUploadQueueHarness.isCanonicalFilename(
      "🔥".repeat(497) + ".pdf",
    ),
    false,
  );

  requests.length = 0;
  const submitItems = [
    makeSubmitItem(1),
    makeSubmitItem(2),
    makeSubmitItem(3),
  ];
  globalThis.__technicalUploadQueueHarness.setSubmitState(
    submitItems,
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  );
  const submitResult = form.dispatch("submit", {preventDefault() {}});
  assert.equal(requests.length, 2, "submit should start two workers");
  requests[0].respond(503, {
    code: "STORED_FILE_STORAGE_FAILURE",
    fatal: true,
    ok: false,
    retryable: true,
  });
  await waitForTurn();
  await waitForTurn();
  assert.equal(requests.length, 2);
  requests[1].respond(422, {
    code: "MALWARE_DETECTED",
    fatal: false,
    ok: false,
    retryable: false,
  });
  await submitResult;

  assert.equal(reconcileCalls, 2, "submit should retry one failed reconciliation");
  assert.equal(requests.length, 2, "no retry or third upload may start");
  assert.equal(submitItems[2].state, "queued");
  assert.equal(
    globalThis.__technicalUploadQueueHarness.requiresRefresh(),
    true,
  );
  assert.equal(fileInput.disabled, true);
  assert.equal(submitButton.disabled, true);
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
