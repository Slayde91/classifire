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
  tokens: Record<string, string>;
};

type VerifiedCall = {
  agentId: string;
  config: PluginConfig;
};

const DEFAULT_BASE_URL = "http://127.0.0.1:8787";
const DEFAULT_TOKEN_FILE = join(homedir(), ".openclaw", "classifire-agent-tokens.json");

const TOOL_AGENTS: Record<string, Set<string>> = {
  classifire_register_evidence_observations: new Set(["cf-intake-evidence"]),
  classifire_submit_initial_physical_model: new Set(["cf-physical-model"]),
  classifire_lock_physical_model: new Set(["cf-physical-model"]),
  classifire_select_repair_strategy: new Set(["cf-technical-system"]),
  classifire_lock_repair_strategy: new Set(["cf-technical-system"]),
  classifire_derive_quantity_labour: new Set(["cf-physical-model"]),
  classifire_required_components: new Set(["cf-commercial-engine"]),
  classifire_derive_commercial: new Set(["cf-commercial-engine"]),
};

const verifiedCalls = new Map<string, VerifiedCall>();

function normalizedBaseUrl(raw: string): string {
  const url = new URL(raw);
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("CLASSIFIRE baseUrl must use http or https");
  }
  if (!["127.0.0.1", "localhost", "::1"].includes(url.hostname)) {
    throw new Error("CLASSIFIRE controlled-write plugin is restricted to a loopback API endpoint");
  }
  return url.toString().replace(/\/$/, "");
}

function parsePluginConfig(value: unknown): PluginConfig {
  const raw = value && typeof value === "object" ? value as Record<string, unknown> : {};
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
    throw new Error(`CLASSIFIRE controlled-write tool ${toolName} has no verified OpenClaw context`);
  }
  const allowed = TOOL_AGENTS[toolName];
  if (!allowed?.has(verified.agentId)) {
    throw new Error(`Agent ${verified.agentId} is not authorised for ${toolName}`);
  }
  return verified;
}

export default definePluginEntry({
  id: "classifire-controlled-write",
  name: "CLASSIFIRE Controlled Write Tools",
  description: "Narrow role-limited write bridge for controlled CLASSIFIRE estimate stages.",
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
            blockReason: `CLASSIFIRE controlled-write role boundary denies ${event.toolName} for ${agentId || "unknown agent"}`,
          };
        }
        const toolCallId = String(event.toolCallId ?? "");
        if (!toolCallId) {
          return {
            block: true,
            blockReason: "CLASSIFIRE controlled-write call has no host-authoritative toolCallId",
          };
        }
        verifiedCalls.set(toolCallId, { agentId, config: pluginConfig });
      },
      { priority: 110, registrationId: "classifire-controlled-write-agent-boundary" },
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
        { optional: true, catalogMode: "direct-only" },
      );
    };

    register(
      "classifire_register_evidence_observations",
      "Append source-preserving page/photo/schedule observations to one editable CLASSIFIRE estimate. The tool may create canonical Defect records but cannot create scope, technical selections, pricing, validation, or release approvals.",
      Type.Object({
        estimate_id: Type.String(),
        observations: Type.Array(Type.Object({
          stored_file_id: Type.String(),
          evidence_type: Type.String(),
          external_defect_id: Type.Optional(Type.String()),
          defect_code: Type.Optional(Type.String()),
          defect_description: Type.Optional(Type.String()),
          defect_location: Type.Optional(Type.String()),
          defect_classification: Type.Optional(Type.String()),
          source_reference: Type.Optional(Type.String()),
          page_number: Type.Optional(Type.String()),
          region_reference: Type.Optional(Type.String()),
          evidence_class: Type.Optional(Type.String()),
          confidence: Type.Optional(Type.Number({ minimum: 0, maximum: 1 })),
          source_json: Type.Optional(Type.Record(Type.String(), Type.Any())),
        })),
      }),
      (agentId, params, config) => classifireRequest(
        config,
        agentId,
        `/api/v1/agent/estimates/${encodeURIComponent(params.estimate_id)}/evidence/register`,
        { method: "POST", body: JSON.stringify({ observations: params.observations }) },
      ),
    );

    register(
      "classifire_submit_initial_physical_model",
      "Submit the one-shot initial canonical opening/service model for an editable estimate. Every Service requires an explicit quantity; omission never defaults to quantity one. The tool cannot select Package 15 systems or pricing.",
      Type.Object({
        estimate_id: Type.String(),
        openings: Type.Array(Type.Object({
          opening_code: Type.String(),
          external_defect_id: Type.Optional(Type.String()),
          location: Type.Optional(Type.String()),
          substrate_type: Type.Optional(Type.String()),
          substrate_plane: Type.Optional(Type.String()),
          substrate_thickness_mm: Type.Optional(Type.Number({ exclusiveMinimum: 0 })),
          orientation: Type.Optional(Type.String()),
          opening_type: Type.Optional(Type.String()),
          width_mm: Type.Optional(Type.Number({ exclusiveMinimum: 0 })),
          height_mm: Type.Optional(Type.Number({ exclusiveMinimum: 0 })),
          diameter_mm: Type.Optional(Type.Number({ exclusiveMinimum: 0 })),
          frl: Type.Optional(Type.String()),
          notes: Type.Optional(Type.String()),
        })),
        services: Type.Array(Type.Object({
          service_code: Type.String(),
          primary_opening_code: Type.String(),
          opening_codes: Type.Array(Type.String()),
          service_type: Type.String(),
          material: Type.Optional(Type.String()),
          nominal_size_mm: Type.Optional(Type.Number({ exclusiveMinimum: 0 })),
          outside_diameter_mm: Type.Optional(Type.Number({ exclusiveMinimum: 0 })),
          width_mm: Type.Optional(Type.Number({ exclusiveMinimum: 0 })),
          height_mm: Type.Optional(Type.Number({ exclusiveMinimum: 0 })),
          insulation_type: Type.Optional(Type.String()),
          insulation_thickness_mm: Type.Optional(Type.Number({ exclusiveMinimum: 0 })),
          quantity: Type.Number({ exclusiveMinimum: 0 }),
          centre_x_mm: Type.Optional(Type.Number()),
          centre_y_mm: Type.Optional(Type.Number()),
          evidence_status: Type.Optional(Type.String()),
          confidence: Type.Optional(Type.Number({ minimum: 0, maximum: 1 })),
          relationship_status: Type.Optional(Type.String()),
          link_type: Type.Optional(Type.String()),
          source_reference: Type.Optional(Type.String()),
          notes: Type.Optional(Type.String()),
        })),
      }),
      (agentId, params, config) => classifireRequest(
        config,
        agentId,
        `/api/v1/agent/estimates/${encodeURIComponent(params.estimate_id)}/physical-model/initial`,
        { method: "POST", body: JSON.stringify({ openings: params.openings, services: params.services }) },
      ),
    );

    register(
      "classifire_lock_physical_model",
      "Create or reuse the deterministic Physical Model Lock after the initial evidence-backed physical model has been submitted. A PROVISIONAL lock does not open Package 15 search.",
      Type.Object({
        estimate_id: Type.String(),
        reason: Type.Optional(Type.String()),
      }),
      (agentId, params, config) => classifireRequest(
        config,
        agentId,
        `/api/v1/agent/estimates/${encodeURIComponent(params.estimate_id)}/physical-model/lock`,
        {
          method: "POST",
          body: JSON.stringify({ reason: params.reason ?? "Controlled cf-physical-model lock request" }),
        },
      ),
    );

    register(
      "classifire_select_repair_strategy",
      "Select one opening-specific Package 15 candidate as the controlled Repair Strategy. Does not perform Human Release or library approval.",
      Type.Object({
        opening_id: Type.String(),
        variant_id: Type.String(),
        match_classification: Type.Optional(Type.String()),
        treatment_description: Type.Optional(Type.String()),
        assumptions: Type.Optional(Type.Array(Type.String())),
        limitations: Type.Optional(Type.Array(Type.String())),
      }),
      (agentId, params, config) => classifireRequest(
        config,
        agentId,
        `/api/v1/agent/openings/${encodeURIComponent(params.opening_id)}/repair-strategy`,
        {
          method: "POST",
          body: JSON.stringify({
            variant_id: params.variant_id,
            match_classification: params.match_classification ?? "opening_specific_candidate",
            treatment_description: params.treatment_description ?? null,
            assumptions: params.assumptions ?? [],
            limitations: params.limitations ?? [],
          }),
        },
      ),
    );

    register(
      "classifire_lock_repair_strategy",
      "Create or reuse the deterministic RepairStrategyLock for an already selected opening-specific Package 15 candidate.",
      Type.Object({ opening_id: Type.String() }),
      (agentId, params, config) => classifireRequest(
        config,
        agentId,
        `/api/v1/agent/openings/${encodeURIComponent(params.opening_id)}/repair-strategy/lock`,
        { method: "POST" },
      ),
    );

    register(
      "classifire_derive_quantity_labour",
      "Run deterministic CLASSIFIRE quantity formulas and pinned-productivity person-hour derivation for an estimate.",
      Type.Object({
        estimate_id: Type.String(),
        component_inputs: Type.Optional(Type.Record(Type.String(), Type.Any())),
        labour_adjustments: Type.Optional(Type.Record(Type.String(), Type.Any())),
      }),
      (agentId, params, config) => classifireRequest(
        config,
        agentId,
        `/api/v1/agent/estimates/${encodeURIComponent(params.estimate_id)}/quantity-labour/derive`,
        {
          method: "POST",
          body: JSON.stringify({
            component_inputs: params.component_inputs ?? {},
            labour_adjustments: params.labour_adjustments ?? {},
          }),
        },
      ),
    );

    register(
      "classifire_required_components",
      "Read the Package 15-derived required components that must be commercially recovered for one estimate.",
      Type.Object({ estimate_id: Type.String() }),
      (agentId, params, config) => classifireRequest(
        config,
        agentId,
        `/api/v1/agent/estimates/${encodeURIComponent(params.estimate_id)}/required-components`,
      ),
    );

    register(
      "classifire_derive_commercial",
      "Run the controlled CLASSIFIRE commercial hierarchy and anti-double-recovery reconciliation for one estimate. A single eligible exact Package 14 match may be auto-selected; near matches are never auto-promoted.",
      Type.Object({
        estimate_id: Type.String(),
        library_selections: Type.Optional(Type.Record(Type.String(), Type.Any())),
        parameterised_selections: Type.Optional(Type.Record(Type.String(), Type.Any())),
        component_builds: Type.Optional(Type.Record(Type.String(), Type.Any())),
        expert_estimates: Type.Optional(Type.Record(Type.String(), Type.Any())),
      }),
      (agentId, params, config) => classifireRequest(
        config,
        agentId,
        `/api/v1/agent/estimates/${encodeURIComponent(params.estimate_id)}/commercial/derive`,
        {
          method: "POST",
          body: JSON.stringify({
            library_selections: params.library_selections ?? {},
            parameterised_selections: params.parameterised_selections ?? {},
            component_builds: params.component_builds ?? {},
            expert_estimates: params.expert_estimates ?? {},
          }),
        },
      ),
    );
  },
});
