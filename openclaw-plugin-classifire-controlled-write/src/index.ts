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

const TOOL_NAME = "classifire_submit_initial_physical_model";
const WRITER_AGENT_ID = "cf-adjudicated-physical-writer";
const DEFAULT_BASE_URL = "http://127.0.0.1:8787";
const DEFAULT_TOKEN_FILE = join(homedir(), ".openclaw", "classifire-agent-tokens.json");
const verifiedCalls = new Map<string, VerifiedCall>();

function normalizedBaseUrl(raw: string): string {
  const url = new URL(raw);
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("CLASSIFIRE baseUrl must use http or https");
  }
  if (!["127.0.0.1", "localhost", "::1"].includes(url.hostname)) {
    throw new Error("CLASSIFIRE admission writer is restricted to a loopback API endpoint");
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

async function loadWriterToken(config: PluginConfig): Promise<string> {
  const raw = await readFile(config.tokenFile, "utf8");
  const parsed = JSON.parse(raw) as TokenFile;
  if (parsed.schema !== "CLASSIFIRE-AGENT-TOKENS-v1") {
    throw new Error("Unexpected CLASSIFIRE agent token-file schema");
  }
  const token = parsed.tokens?.[WRITER_AGENT_ID];
  if (!token) {
    throw new Error(`No CLASSIFIRE service token configured for ${WRITER_AGENT_ID}`);
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

async function submitAdmission(
  config: PluginConfig,
  params: { admission_id: string; idempotency_key: string },
): Promise<ReturnType<typeof asToolResult>> {
  const token = await loadWriterToken(config);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 60_000);
  try {
    const response = await fetch(`${normalizedBaseUrl(config.baseUrl)}/api/v1/agent/physical-model/initial`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "X-Classifire-Agent-ID": WRITER_AGENT_ID,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        admission_id: params.admission_id,
        idempotency_key: params.idempotency_key,
      }),
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

function requireVerifiedCall(toolCallId: string): VerifiedCall {
  const verified = verifiedCalls.get(toolCallId);
  if (!verified) {
    throw new Error(`CLASSIFIRE controlled-write tool ${TOOL_NAME} has no verified OpenClaw context`);
  }
  if (verified.agentId !== WRITER_AGENT_ID) {
    throw new Error(`Agent ${verified.agentId} is not authorised for ${TOOL_NAME}`);
  }
  return verified;
}

export default definePluginEntry({
  id: "classifire-controlled-write",
  name: "CLASSIFIRE Admission Writer",
  description: "Admission-only bridge for one controlled initial physical-model submission.",
  configSchema: pluginConfigSchema,
  register(api: any) {
    const pluginConfig = parsePluginConfig(api.pluginConfig);
    api.on(
      "before_tool_call",
      async (event: any, ctx: any) => {
        if (event.toolName !== TOOL_NAME) return;
        const agentId = String(ctx?.agentId ?? "");
        const sessionKey = String(ctx?.sessionKey ?? "");
        if (agentId !== WRITER_AGENT_ID) {
          return {
            block: true,
            blockReason: `CLASSIFIRE admission writer denies ${TOOL_NAME} for ${agentId || "unknown agent"}`,
          };
        }
        if (!sessionKey) {
          return {
            block: true,
            blockReason: "CLASSIFIRE admission writer requires host-authoritative sessionKey",
          };
        }
        if (sessionKey.endsWith("-21-visual-physical")) {
          return {
            block: true,
            blockReason: `CLASSIFIRE visual Physical session denies ${TOOL_NAME}`,
          };
        }
        const toolCallId = String(event.toolCallId ?? "");
        if (!toolCallId) {
          return {
            block: true,
            blockReason: "CLASSIFIRE admission writer call has no host-authoritative toolCallId",
          };
        }
        verifiedCalls.set(toolCallId, { agentId, config: pluginConfig });
      },
      { priority: 110, registrationId: "classifire-admission-writer-agent-boundary" },
    );

    api.registerTool(
      {
        name: TOOL_NAME,
        description: "Consume one pre-registered signed admission. Accepts no physical facts and creates no Physical Model Lock.",
        parameters: Type.Object({
          admission_id: Type.String({ minLength: 36, maxLength: 100 }),
          idempotency_key: Type.String({ minLength: 16, maxLength: 200 }),
        }, { additionalProperties: false }),
        async execute(
          toolCallId: string,
          params: { admission_id: string; idempotency_key: string },
        ) {
          const verified = requireVerifiedCall(toolCallId);
          try {
            return await submitAdmission(verified.config, params);
          } finally {
            verifiedCalls.delete(toolCallId);
          }
        },
      },
      { optional: true, catalogMode: "direct-only" },
    );
  },
});
