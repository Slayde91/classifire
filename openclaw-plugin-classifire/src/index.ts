import { readFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import { Type } from "typebox";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

type PluginConfig = {
  baseUrl: string;
  tokenFile: string;
};

type TokenFile = {
  schema: string;
  base_url?: string;
  tokens: Record<string, string>;
};

type VerifiedCall = {
  agentId: string;
  config: PluginConfig;
};

const DEFAULT_BASE_URL = "http://127.0.0.1:8787";
const DEFAULT_TOKEN_FILE = join(homedir(), ".openclaw", "classifire-agent-tokens.json");

const ALL_CF_AGENTS = new Set([
  "cf-orchestrator",
  "cf-intake-evidence",
  "cf-physical-model",
  "cf-technical-system",
  "cf-commercial-engine",
  "cf-validator",
  "cf-output",
  "cf-library-governance",
  "cf-platform-governance",
]);

const TOOL_AGENTS: Record<string, Set<string>> = {
  classifire_health: ALL_CF_AGENTS,
  classifire_workflow_status: ALL_CF_AGENTS,
  classifire_evidence_read: new Set(["cf-intake-evidence"]),
  classifire_physical_model_read: new Set(["cf-physical-model"]),
  classifire_technical_search: new Set(["cf-technical-system"]),
  classifire_package14_recommendation: new Set(["cf-commercial-engine"]),
  classifire_run_validation: new Set(["cf-validator"]),
  classifire_lock_snapshot: new Set(["cf-output"]),
  classifire_render_output: new Set(["cf-output"]),
  classifire_library_releases: new Set(["cf-library-governance"]),
};

const verifiedCalls = new Map<string, VerifiedCall>();

function normalizedBaseUrl(raw: string): string {
  const url = new URL(raw);
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("CLASSIFIRE baseUrl must use http or https");
  }
  if (!["127.0.0.1", "localhost", "::1"].includes(url.hostname)) {
    throw new Error("CLASSIFIRE tool plugin is restricted to a loopback API endpoint");
  }
  return url.toString().replace(/\/$/, "");
}

function parsePluginConfig(value: unknown): PluginConfig {
  const raw = value && typeof value === "object"
    ? value as Record<string, unknown>
    : {};
  const baseUrl = String(raw.baseUrl ?? DEFAULT_BASE_URL);
  const tokenFile = String(raw.tokenFile ?? DEFAULT_TOKEN_FILE);
  normalizedBaseUrl(baseUrl);
  if (!tokenFile.trim()) {
    throw new Error("CLASSIFIRE tokenFile cannot be blank");
  }
  return { baseUrl, tokenFile };
}

const pluginConfigSchema = {
  parse: parsePluginConfig,
  jsonSchema: {
    type: "object",
    additionalProperties: false,
    properties: {
      baseUrl: { type: "string" },
      tokenFile: { type: "string" },
    },
  },
};

async function loadToken(config: PluginConfig, agentId: string): Promise<string> {
  const raw = await readFile(config.tokenFile, "utf8");
  const parsed = JSON.parse(raw) as TokenFile;
  if (parsed.schema !== "CLASSIFIRE-AGENT-TOKENS-v1") {
    throw new Error("Unexpected CLASSIFIRE agent token-file schema");
  }
  const token = parsed.tokens?.[agentId];
  if (!token) {
    throw new Error(`No CLASSIFIRE service token configured for ${agentId}`);
  }
  return token;
}

function asToolResult(body: unknown) {
  const text = typeof body === "string" ? body : JSON.stringify(body, null, 2);
  return {
    content: [{ type: "text" as const, text }],
    details: body,
  };
}

async function classifireRequest(
  config: PluginConfig,
  agentId: string,
  path: string,
  init: RequestInit = {},
): Promise<ReturnType<typeof asToolResult>> {
  const baseUrl = normalizedBaseUrl(config.baseUrl);
  const token = await loadToken(config, agentId);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 60_000);
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers: {
        "Authorization": `Bearer ${token}`,
        "X-Classifire-Agent-ID": agentId,
        "Content-Type": "application/json",
        ...(init.headers ?? {}),
      },
      signal: controller.signal,
    });
    const text = await response.text();
    let body: unknown = text;
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        body = text;
      }
    }
    if (!response.ok) {
      throw new Error(
        `CLASSIFIRE API ${response.status} ${response.statusText}: ${JSON.stringify(body)}`,
      );
    }
    return asToolResult(body);
  } finally {
    clearTimeout(timeout);
  }
}

function requireVerifiedCall(toolCallId: string, toolName: string): VerifiedCall {
  const verified = verifiedCalls.get(toolCallId);
  if (!verified) {
    throw new Error(`CLASSIFIRE tool ${toolName} has no verified OpenClaw tool-call context`);
  }
  const allowed = TOOL_AGENTS[toolName];
  if (!allowed?.has(verified.agentId)) {
    throw new Error(`Agent ${verified.agentId} is not authorised for ${toolName}`);
  }
  return verified;
}

export default definePluginEntry({
  id: "classifire-tools",
  name: "CLASSIFIRE Tools",
  description: "Role-limited bridge from OpenClaw agents to the canonical CLASSIFIRE API.",
  configSchema: pluginConfigSchema,
  register(api: any) {
    const pluginConfig = parsePluginConfig(api.pluginConfig);

    api.on(
      "before_tool_call",
      async (event: any, ctx: any) => {
        const allowed = TOOL_AGENTS[event.toolName];
        if (!allowed) return;
        const agentId = String(ctx?.agentId ?? "");
        if (!agentId || !allowed.has(agentId)) {
          return {
            block: true,
            blockReason: `CLASSIFIRE role boundary denies ${event.toolName} for ${agentId || "unknown agent"}`,
          };
        }
        const toolCallId = String(event.toolCallId ?? "");
        if (!toolCallId) {
          return {
            block: true,
            blockReason: "CLASSIFIRE tool call has no host-authoritative toolCallId",
          };
        }
        verifiedCalls.set(toolCallId, { agentId, config: pluginConfig });
      },
      { priority: 100, registrationId: "classifire-agent-boundary" },
    );

    const register = (
      name: string,
      description: string,
      parameters: any,
      executeRequest: (
        agentId: string,
        params: any,
        config: PluginConfig,
      ) => Promise<ReturnType<typeof asToolResult>>,
    ) => {
      api.registerTool(
        {
          name,
          description,
          parameters,
          async execute(toolCallId: string, params: any) {
            const verified = requireVerifiedCall(toolCallId, name);
            try {
              return await executeRequest(verified.agentId, params, verified.config);
            } finally {
              verifiedCalls.delete(toolCallId);
            }
          },
        },
        { optional: true },
      );
    };

    register(
      "classifire_health",
      "Read the authenticated CLASSIFIRE service status for the current role agent.",
      Type.Object({}),
      (agentId, _params, config) => classifireRequest(config, agentId, "/api/v1/agent/health"),
    );

    register(
      "classifire_workflow_status",
      "Read canonical CLASSIFIRE workflow stage, facts, and blockers for one estimate.",
      Type.Object({ estimate_id: Type.String() }),
      (agentId, params, config) =>
        classifireRequest(config, agentId, `/api/v1/agent/estimates/${encodeURIComponent(params.estimate_id)}/workflow`),
    );

    register(
      "classifire_evidence_read",
      "Read retained evidence metadata for one CLASSIFIRE estimate. Does not ingest or mutate evidence.",
      Type.Object({ estimate_id: Type.String() }),
      (agentId, params, config) =>
        classifireRequest(config, agentId, `/api/v1/agent/estimates/${encodeURIComponent(params.estimate_id)}/evidence`),
    );

    register(
      "classifire_physical_model_read",
      "Read the canonical openings, services, dimensions, evidence links, and active Physical Model Locks for an estimate.",
      Type.Object({ estimate_id: Type.String() }),
      (agentId, params, config) =>
        classifireRequest(config, agentId, `/api/v1/agent/estimates/${encodeURIComponent(params.estimate_id)}/physical-model`),
    );

    register(
      "classifire_technical_search",
      "Run guarded opening-specific Package 15 technical candidate search. Candidate output is not approval.",
      Type.Object({ opening_id: Type.String() }),
      (agentId, params, config) =>
        classifireRequest(config, agentId, `/api/v1/agent/openings/${encodeURIComponent(params.opening_id)}/technical-search`),
    );

    register(
      "classifire_package14_recommendation",
      "Return exact and suggested near Package 14 matches for a required component. Near matches are commercial analogues only unless separately approved through controlled parameterisation.",
      Type.Object({ component_id: Type.String() }),
      (agentId, params, config) =>
        classifireRequest(
          config,
          agentId,
          `/api/v1/agent/required-components/${encodeURIComponent(params.component_id)}/package14-recommendation`,
        ),
    );

    register(
      "classifire_run_validation",
      "Run CLASSIFIRE's deterministic independent final validator for an estimate. The tool cannot alter upstream scope or pricing to make validation pass.",
      Type.Object({ estimate_id: Type.String() }),
      (agentId, params, config) =>
        classifireRequest(
          config,
          agentId,
          `/api/v1/agent/estimates/${encodeURIComponent(params.estimate_id)}/independent-validation`,
          { method: "POST" },
        ),
    );

    register(
      "classifire_lock_snapshot",
      "Create or reuse the immutable validated CLASSIFIRE snapshot after a current independent-validation PASS.",
      Type.Object({
        estimate_id: Type.String(),
        reason: Type.Optional(Type.String()),
      }),
      (agentId, params, config) =>
        classifireRequest(
          config,
          agentId,
          `/api/v1/agent/estimates/${encodeURIComponent(params.estimate_id)}/lock`,
          {
            method: "POST",
            body: JSON.stringify({ reason: params.reason ?? "Controlled cf-output snapshot request" }),
          },
        ),
    );

    register(
      "classifire_render_output",
      "Render a controlled CLASSIFIRE PDF/XLSX from the current immutable validated snapshot and return its audit receipt. Does not perform Human Release.",
      Type.Object({
        estimate_id: Type.String(),
        artifact_type: Type.Union([
          Type.Literal("technical-xlsx"),
          Type.Literal("proposal-xlsx"),
          Type.Literal("technical-pdf"),
          Type.Literal("proposal-pdf"),
        ]),
      }),
      (agentId, params, config) =>
        classifireRequest(
          config,
          agentId,
          `/api/v1/agent/estimates/${encodeURIComponent(params.estimate_id)}/render`,
          { method: "POST", body: JSON.stringify({ artifact_type: params.artifact_type }) },
        ),
    );

    register(
      "classifire_library_releases",
      "Read governed CLASSIFIRE library release metadata and hashes. Does not create, approve, activate, or supersede releases.",
      Type.Object({}),
      (agentId, _params, config) => classifireRequest(config, agentId, "/api/v1/agent/library/releases"),
    );
  },
});
