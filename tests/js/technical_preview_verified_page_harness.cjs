"use strict";

const assert = require("node:assert/strict");
const {createHash, webcrypto} = require("node:crypto");
const fs = require("node:fs");
const {TextEncoder} = require("node:util");
const vm = require("node:vm");

const productionScript = process.argv[2];
assert.ok(productionScript, "expected the technical-preview.js path");
const source = fs.readFileSync(productionScript, "utf8").replaceAll("\r\n", "\n");

class ListenerTarget {
  constructor() {
    this.attributes = new Map();
    this.listeners = new Map();
  }

  addEventListener(name, callback) {
    const callbacks = this.listeners.get(name) || [];
    callbacks.push(callback);
    this.listeners.set(name, callbacks);
  }

  dispatchEvent(event) {
    for (const callback of this.listeners.get(event.type) || []) {
      callback(event);
    }
    return true;
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  removeAttribute(name) {
    this.attributes.delete(name);
    delete this[name];
  }

  focus() {}
}

const control = () => Object.assign(new ListenerTarget(), {
  disabled: false,
  isConnected: true,
  value: "",
});

const sha256 = (value) => createHash("sha256").update(value).digest("hex");

const previewPng = () => {
  const png = Buffer.alloc(33);
  Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]).copy(png, 0);
  Buffer.from([0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52]).copy(png, 8);
  png.writeUInt32BE(1, 16);
  png.writeUInt32BE(1, 20);
  return png;
};

const waitForTurn = () => new Promise((resolve) => setImmediate(resolve));

const runPreview = async ({validBinding}) => {
  const operations = [];
  const verifiedEvents = [];
  const sourceSha256 = "a".repeat(64);
  const sourceSize = 41;
  const png = previewPng();
  const pngSha256 = sha256(png);
  const receipt = {
    height_pixels: 1,
    page_count: 2,
    page_number: 1,
    png_sha256: pngSha256,
    policy_version: "technical-pdf-preview-v1",
    renderer: "PyMuPDF",
    renderer_version: "1.0",
    source_sha256: sourceSha256,
    source_size_bytes: sourceSize,
    width_pixels: 1,
  };
  const bindingSha256 = validBinding
    ? sha256(JSON.stringify(receipt))
    : "0".repeat(64);

  const previousButton = control();
  const nextButton = control();
  const loadButton = control();
  const fitButton = control();
  const actualButton = control();
  const pageInput = Object.assign(control(), {value: "1"});
  const pageCountLabel = {textContent: ""};
  const status = {textContent: ""};
  const stage = control();
  const image = Object.assign(new ListenerTarget(), {
    alt: "",
    classList: {toggle() {}},
    hidden: true,
    async decode() {
      operations.push("decode");
    },
  });
  const controls = new Map([
    ["[data-preview-previous]", previousButton],
    ["[data-preview-next]", nextButton],
    ["[data-preview-load]", loadButton],
    ["[data-preview-fit]", fitButton],
    ["[data-preview-actual]", actualButton],
    ["[data-preview-page]", pageInput],
    ["[data-preview-page-count]", pageCountLabel],
    ["[data-preview-status]", status],
    [".technical-preview-stage", stage],
    ["[data-preview-image]", image],
  ]);
  const host = Object.assign(new ListenerTarget(), {
    dataset: {
      maxPages: "500",
      previewUrlPrefix: "/technical/documents/source/preview/",
      sourceSha256,
      sourceSize: String(sourceSize),
    },
    append() {},
    querySelector(selector) {
      return controls.get(selector) || null;
    },
  });
  host.addEventListener(
    "classifire:technical-preview-page-verified",
    (event) => {
      operations.push("dispatch");
      verifiedEvents.push(event);
    },
  );

  const responseHeaders = new Map(Object.entries({
    "cache-control": "private, no-store",
    "content-length": String(png.byteLength),
    "content-type": "image/png",
    "x-classifire-preview-binding-sha256": bindingSha256,
    "x-classifire-preview-height": "1",
    "x-classifire-preview-page": "1",
    "x-classifire-preview-page-count": "2",
    "x-classifire-preview-png-sha256": pngSha256,
    "x-classifire-preview-policy": "technical-pdf-preview-v1",
    "x-classifire-preview-renderer": "PyMuPDF/1.0",
    "x-classifire-preview-width": "1",
    "x-classifire-source-sha256": sourceSha256,
    "x-classifire-source-size": String(sourceSize),
    "x-content-type-options": "nosniff",
  }));

  class FakeFileReader extends ListenerTarget {
    readAsDataURL(blob) {
      blob.arrayBuffer().then((buffer) => {
        this.result = `data:image/png;base64,${Buffer.from(buffer).toString("base64")}`;
        this.dispatchEvent({type: "load"});
      });
    }
  }

  class FakeCustomEvent {
    constructor(type, options) {
      this.bubbles = options.bubbles;
      this.detail = options.detail;
      this.type = type;
    }
  }

  const context = {
    AbortController,
    Blob,
    CustomEvent: FakeCustomEvent,
    DataView,
    FileReader: FakeFileReader,
    TextEncoder,
    Uint8Array,
    clearTimeout,
    console,
    crypto: webcrypto,
    document: {
      createElement() {
        return new ListenerTarget();
      },
      querySelector(selector) {
        return selector === "[data-technical-pdf-preview]" ? host : null;
      },
    },
    async fetch() {
      return {
        async arrayBuffer() {
          return png.buffer.slice(png.byteOffset, png.byteOffset + png.byteLength);
        },
        headers: {get: (name) => responseHeaders.get(name.toLowerCase()) || null},
        ok: true,
        status: 200,
      };
    },
    setTimeout,
  };
  vm.createContext(context);
  vm.runInContext(source, context, {filename: productionScript});

  for (let turn = 0; turn < 20 && host.attributes.get("aria-busy") !== "false"; turn += 1) {
    await waitForTurn();
  }
  return {host, image, operations, status, verifiedEvents};
};

(async () => {
  const success = await runPreview({validBinding: true});
  assert.equal(success.verifiedEvents.length, 1);
  assert.deepEqual(success.operations, ["decode", "dispatch"]);
  assert.equal(success.image.hidden, false);
  assert.equal(success.verifiedEvents[0].bubbles, true);
  assert.equal(success.verifiedEvents[0].detail.pageNumber, 1);
  assert.equal(success.verifiedEvents[0].detail.pageCount, 2);
  assert.equal(success.verifiedEvents[0].detail.sourceSha256, "a".repeat(64));
  assert.equal(success.verifiedEvents[0].detail.sourceSize, 41);
  assert.equal(Object.isFrozen(success.verifiedEvents[0].detail), true);

  const failure = await runPreview({validBinding: false});
  assert.equal(failure.verifiedEvents.length, 0);
  assert.deepEqual(failure.operations, []);
  assert.equal(failure.image.hidden, true);
  assert.match(failure.status.textContent, /could not be confirmed/i);
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
