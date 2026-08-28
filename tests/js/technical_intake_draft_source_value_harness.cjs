"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const productionScript = process.argv[2];
assert.ok(productionScript, "expected the technical-intake-draft.js path");
const source = fs.readFileSync(productionScript, "utf8").replaceAll("\r\n", "\n");
const start = source.indexOf("  const normalizedTextareaValue =");
const end = source.indexOf("  const setValue =", start);
assert.notEqual(start, -1, "source-value normalization helper changed");
assert.notEqual(end, -1, "source-value helper boundary changed");
const helperSource = source.slice(start, end);
vm.runInThisContext(
  [
    '"use strict";',
    'const retainedSourceValue = Symbol("retainedSourceValue");',
    helperSource,
    "globalThis.__technicalIntakeSourceValueHarness = {",
    "  rememberSourceValue, sourceValueOrNull,",
    "};",
  ].join("\n"),
  {filename: productionScript},
);

const helpers = globalThis.__technicalIntakeSourceValueHarness;
const unchanged = {value: "  copied line\nsecond line\n"};
helpers.rememberSourceValue(unchanged, "  copied line\r\nsecond line\r\n");
assert.equal(
  helpers.sourceValueOrNull(unchanged),
  "  copied line\r\nsecond line\r\n",
  "an unchanged textarea must retain exact persisted source wording",
);

unchanged.value = "  edited line\nsecond line\n";
assert.equal(
  helpers.sourceValueOrNull(unchanged),
  "  edited line\nsecond line\n",
  "an edited textarea must return the current source wording",
);

const blank = {value: ""};
helpers.rememberSourceValue(blank, null);
assert.equal(helpers.sourceValueOrNull(blank), null);
