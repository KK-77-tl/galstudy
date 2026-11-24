import test from "node:test";
import assert from "node:assert/strict";
import { timingSafeEqual } from "node:crypto";
import worker, { openAIStream } from "./worker.mjs";

// Node lacks the Workers extension. Live HTTPS checks also exercise the real API.
crypto.subtle.timingSafeEqual = (a, b) => timingSafeEqual(Buffer.from(a), Buffer.from(b));
const model = "@cf/zai-org/glm-4.7-flash";
const payload = { model, messages: [{ role: "user", content: "hello" }], max_tokens: 100, stream: false };
const req = (body = payload, auth = "Bearer test-secret") => new Request("https://example.com/v1/chat/completions", {
  method: "POST", headers: { Authorization: auth, "Content-Type": "application/json" }, body: JSON.stringify(body),
});
const env = { GATEWAY_TOKEN: "test-secret", AI: { run: async () => { throw new Error("should not run"); } } };

test("unauthenticated requests never reach AI", async () => {
  assert.equal((await worker.fetch(req(payload, "Bearer wrong"), env)).status, 401);
  assert.equal((await worker.fetch(req(), { ...env, GATEWAY_TOKEN: "" })).status, 401);
});

test("unsupported models, tool inputs, and oversized bodies never reach AI", async () => {
  for (const p of [{ ...payload, model: "external" }, { ...payload, tools: [] }, { ...payload, max_tokens: 8193 }]) {
    assert.equal((await worker.fetch(req(p), env)).status, 400);
  }
  assert.equal((await worker.fetch(req({ ...payload, messages: [{ role: "user", content: "x".repeat(66000) }] }), env)).status, 413);
});

test("structured output and usage survive conversion, ceiling reports length", async () => {
  const actual = { ...env, AI: { run: async (name, input, options) => {
    assert.equal(name, model);
    assert.equal(input.response_format.type, "json_object");
    assert.equal(input.max_completion_tokens, 100);
    assert.equal(input.chat_template_kwargs.enable_thinking, false);
    assert.deepEqual(options, { rejectIfBusy: true });
    assert.equal(Object.hasOwn(input, "rejectIfBusy"), false);
    return { choices: [{ message: { content: JSON.stringify({ answer: "主动回忆" }) }, finish_reason: "length" }], usage: { completion_tokens: 100 } };
  } } };
  const r = await worker.fetch(req({ ...payload, response_format: { type: "json_object" } }), actual);
  const body = await r.json();
  assert.equal(body.choices[0].finish_reason, "length");
  assert.deepEqual(JSON.parse(body.choices[0].message.content), { answer: "主动回忆" });
  assert.equal(r.headers.get("Cache-Control"), "no-store");
});

function native(parts) {
  const encoded = new TextEncoder().encode(parts);
  return new ReadableStream({ start(c) {
    // Byte splits deliberately cut multibyte Chinese and SSE lines.
    for (let i = 0; i < encoded.length; i += 3) c.enqueue(encoded.slice(i, i + 3));
    c.close();
  } });
}

test("stream conversion handles UTF-8 fragments, CRLF and DONE", async () => {
  const r = new Response(openAIStream(native('data: {"response":"课程知识"}\r\n\r\ndata: [DONE]\n\n'), model));
  const text = await r.text();
  assert.ok(text.includes('"content":"课程知识"'));
  assert.ok(text.endsWith("data: [DONE]\n\n"));
});

test("truncated or explicit failed upstream streams cannot appear complete", async () => {
  await assert.rejects(new Response(openAIStream(native('data: {"response":"partial"}\n\n'), model)).text(), /truncated/);
  await assert.rejects(new Response(openAIStream(native('data: {"error":"failed"}\n\ndata: [DONE]\n\n'), model)).text(), /stream_error/);
});

test("upstream exceptions expose no service details", async () => {
  const r = await worker.fetch(req(), env);
  assert.equal(r.status, 502);
  assert.equal((await r.json()).error.message, "Model unavailable");
});
