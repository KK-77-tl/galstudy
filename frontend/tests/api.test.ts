import assert from "node:assert/strict";
import { test } from "node:test";
import { api } from "../lib/api.ts";

test("JSON headers, FormData and caller cancellation reach fetch", async (t) => {
  const calls: RequestInit[] = [];
  t.mock.method(
    globalThis,
    "fetch",
    async (_url: string, options: RequestInit) => {
      calls.push(options);
      return Response.json({ ok: true });
    },
  );
  const controller = new AbortController();
  await api("/courses", {
    method: "POST",
    body: "{}",
    signal: controller.signal,
  });
  assert.equal(
    new Headers(calls[0].headers).get("Content-Type"),
    "application/json",
  );
  assert.equal(calls[0].signal, controller.signal);
  await api("/courses/id/files", { body: new FormData(), method: "POST" });
  assert.equal(new Headers(calls[1].headers).has("Content-Type"), false);
});

test("API errors preserve server messages and safely handle validation details", async (t) => {
  t.mock.method(globalThis, "fetch", async () =>
    Response.json({ detail: "今日额度已用完" }, { status: 429 }),
  );
  await assert.rejects(api("/courses"), /今日额度已用完/);
  t.mock.method(globalThis, "fetch", async () =>
    Response.json({ detail: [{ msg: "invalid" }] }, { status: 422 }),
  );
  await assert.rejects(api("/courses"), /请求失败/);
});

for (const boundary of ["logout", "login", "register"]) {
  test(`late private data is rejected after ${boundary}`, async (t) => {
    let finish!: (value: Response) => void;
    t.mock.method(globalThis, "fetch", (url: string) => {
      if (url === "/api/courses")
        return new Promise<Response>((resolve) => {
          finish = resolve;
        });
      return Promise.resolve(Response.json({ email: "new@example.com" }));
    });
    const pending = api("/courses");
    await api(`/auth/${boundary}`, { method: "POST" });
    finish(Response.json([{ title: "旧账号私有课程" }]));
    await assert.rejects(pending, {
      name: "AbortError",
      message: "账号会话已切换",
    });
  });
}
