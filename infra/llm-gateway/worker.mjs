// Private OpenAI-compatible adapter for the existing FastAPI providers.
const MODEL = "@cf/zai-org/glm-4.7-flash";
const LIMIT = 65536;
const headers = { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" };

function error(message, status) {
  return Response.json({ error: { message } }, { status, headers });
}

async function authorized(request, secret) {
  if (!secret) return false;
  const encoder = new TextEncoder();
  const hashes = await Promise.all([
    crypto.subtle.digest("SHA-256", encoder.encode(request.headers.get("Authorization") || "")),
    crypto.subtle.digest("SHA-256", encoder.encode("Bearer " + secret)),
  ]);
  return crypto.subtle.timingSafeEqual(hashes[0], hashes[1]);
}

async function boundedJson(request) {
  const reader = request.body?.getReader();
  if (!reader) throw new Error("invalid_body");
  const chunks = [];
  let size = 0;
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > LIMIT) throw new Error("body_limit");
      chunks.push(value);
    }
  } catch (e) {
    await reader.cancel().catch(() => {});
    throw e;
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
}

function validate(p) {
  if (!p || p.model !== MODEL || !Array.isArray(p.messages) || !p.messages.length || p.messages.length > 12) return false;
  if (p.messages.some(m => !m || !["system", "user", "assistant"].includes(m.role) || typeof m.content !== "string" || !m.content.length)) return false;
  if (!Number.isInteger(p.max_tokens) || p.max_tokens < 1 || p.max_tokens > 8192) return false;
  if (typeof p.stream !== "boolean") return false;
  if (p.response_format && (p.stream || p.response_format.type !== "json_object" || Object.keys(p.response_format).length !== 1)) return false;
  return Object.keys(p).every(k => ["model", "messages", "stream", "max_tokens", "response_format"].includes(k));
}

function usageLog(usage, stream) {
  if (usage) console.log(JSON.stringify({ event: "model_usage", stream, usage }));
}

// Native Workers AI emits response fragments; the app consumes OpenAI deltas.
export function openAIStream(native, model) {
  let pending = "", complete = false;
  const encoder = new TextEncoder();
  const emit = (controller, value) => controller.enqueue(encoder.encode("data: " + JSON.stringify(value) + "\n\n"));
  function line(raw, controller) {
    if (!raw.startsWith("data:")) return;
    const body = raw.slice(5).trim();
    if (!body || complete) return;
    if (body === "[DONE]") {
      complete = true;
      controller.enqueue(encoder.encode("data: [DONE]\n\n"));
      return;
    }
    const item = JSON.parse(body);
    if (item.error || item.errors?.length) throw new Error("upstream_stream_error");
    usageLog(item.usage, true);
    if (item.choices) emit(controller, item);
    else if (typeof item.response === "string" && item.response) {
      emit(controller, { model, choices: [{ index: 0, delta: { content: item.response }, finish_reason: null }] });
    }
  }
  return native.pipeThrough(new TextDecoderStream()).pipeThrough(new TransformStream({
    transform(part, controller) {
      pending += part;
      if (pending.length > LIMIT) throw new Error("upstream_event_limit");
      const lines = pending.split("\n");
      pending = lines.pop();
      for (const raw of lines) line(raw.replace(/\r$/, ""), controller);
    },
    flush(controller) {
      if (pending) line(pending.replace(/\r$/, ""), controller);
      if (!complete) throw new Error("upstream_stream_truncated");
    },
  }));
}

export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname;
    if (path === "/health" && request.method === "GET") return Response.json({ status: "ok", provider: "workers-ai" }, { headers });
    if (path !== "/v1/chat/completions") return error("Not found", 404);
    if (request.method !== "POST") return error("Method not allowed", 405);
    if (!(await authorized(request, env.GATEWAY_TOKEN))) return error("Unauthorized", 401);
    if (!(request.headers.get("Content-Type") || "").toLowerCase().startsWith("application/json")) return error("JSON required", 415);
    let payload;
    try { payload = await boundedJson(request); }
    catch (e) { return error(e.message === "body_limit" ? "Body too large" : "Invalid JSON", e.message === "body_limit" ? 413 : 400); }
    if (!validate(payload)) return error("Invalid model or request", 400);
    try {
      const input = {
        messages: payload.messages, stream: payload.stream,
        max_completion_tokens: payload.max_tokens, temperature: 0.3,
        chat_template_kwargs: { enable_thinking: false },
      };
      if (payload.response_format) input.response_format = payload.response_format;
      // The application has a bounded request deadline; do not wait in a
      // capacity queue when inference cannot start. This is a binding option,
      // separate from model input (including for streamed responses).
      const result = await env.AI.run(MODEL, input, { rejectIfBusy: true });
      if (payload.stream) return new Response(openAIStream(result, MODEL), { headers: { ...headers, "Content-Type": "text/event-stream" } });
      usageLog(result.usage, false);
      const choice = result.choices?.[0];
      const content = choice?.message?.content;
      if (typeof content !== "string" || !content) return error("Empty model output", 502);
      return Response.json({
        model: MODEL,
        choices: [{ index: 0, message: { role: "assistant", content }, finish_reason: choice.finish_reason }],
        usage: result.usage,
      }, { headers });
    } catch {
      console.error(JSON.stringify({ event: "model_request_failed" }));
      return error("Model unavailable", 502);
    }
  },
};
