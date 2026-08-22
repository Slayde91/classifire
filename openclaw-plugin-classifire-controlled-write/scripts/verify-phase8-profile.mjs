import assert from "node:assert/strict";

import plugin from "../dist/index.js";

const ADMISSION_TOOL = "classifire_submit_initial_physical_model";
const ALL_SOURCE_TOOLS = [
  "classifire_register_evidence_observations",
  ADMISSION_TOOL,
  "classifire_select_repair_strategy",
  "classifire_lock_repair_strategy",
  "classifire_derive_quantity_labour",
  "classifire_required_components",
  "classifire_derive_commercial",
];

function loadProfile(deploymentProfile) {
  const hooks = new Map();
  const registered = [];
  const pluginConfig = deploymentProfile === undefined
    ? {}
    : { deploymentProfile };

  plugin.register({
    pluginConfig,
    on(name, handler) {
      hooks.set(name, handler);
    },
    registerTool(tool) {
      registered.push(tool);
    },
  });

  return { hooks, registered };
}

const phase8 = loadProfile("phase8-admission-only");
assert.deepEqual(
  phase8.registered.map((tool) => tool.name),
  [ADMISSION_TOOL],
  "Phase 8 must register exactly the admission tool",
);

const defaultProfile = loadProfile(undefined);
assert.deepEqual(
  defaultProfile.registered.map((tool) => tool.name),
  [ADMISSION_TOOL],
  "The omitted profile must fail closed to Phase 8 admission-only",
);

const submissionSchema = phase8.registered[0].parameters;
assert.deepEqual(
  [...submissionSchema.required].sort(),
  ["admission_id", "estimate_id", "idempotency_key"],
);
assert.equal(submissionSchema.additionalProperties, false);

const beforeToolCall = phase8.hooks.get("before_tool_call");
assert.equal(typeof beforeToolCall, "function");

const inactive = await beforeToolCall(
  {
    toolName: "classifire_register_evidence_observations",
    toolCallId: "inactive-tool-call",
  },
  { agentId: "cf-intake-evidence", sessionKey: "agent:cf-intake-evidence:main" },
);
assert.equal(inactive.block, true);
assert.match(inactive.blockReason, /leaves .* inactive/);

const wrongAgent = await beforeToolCall(
  { toolName: ADMISSION_TOOL, toolCallId: "wrong-agent-call" },
  { agentId: "cf-validator", sessionKey: "agent:cf-validator:main" },
);
assert.equal(wrongAgent.block, true);
assert.match(wrongAgent.blockReason, /role boundary denies/);

const visualSession = await beforeToolCall(
  { toolName: ADMISSION_TOOL, toolCallId: "visual-session-call" },
  {
    agentId: "cf-physical-model",
    sessionKey: "agent:cf-physical-model:main-21-visual-physical",
  },
);
assert.equal(visualSession.block, true);
assert.match(visualSession.blockReason, /visual Physical session denies/);

const validAdmission = await beforeToolCall(
  { toolName: ADMISSION_TOOL, toolCallId: "valid-admission-call" },
  { agentId: "cf-physical-model", sessionKey: "agent:cf-physical-model:main" },
);
assert.equal(validAdmission, undefined);

const full = loadProfile("full-controlled-write");
assert.deepEqual(
  full.registered.map((tool) => tool.name).sort(),
  [...ALL_SOURCE_TOOLS].sort(),
  "The explicit full profile must preserve all broader source tools",
);

assert.throws(
  () => loadProfile("unsupported-profile"),
  /Unsupported CLASSIFIRE deploymentProfile/,
);
assert.throws(
  () => loadProfile("toString"),
  /Unsupported CLASSIFIRE deploymentProfile/,
  "Inherited object properties must not be accepted as deployment profiles",
);

console.log("Phase 8 admission-only runtime profile verification: PASS");
