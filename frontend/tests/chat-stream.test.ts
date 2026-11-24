import assert from "node:assert/strict";
import { test } from "node:test";
import { chatEvents } from "../lib/chat-stream.ts";

function stream(text: string, chunkSize = 1) {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (let offset = 0; offset < bytes.length; offset += chunkSize)
        controller.enqueue(bytes.slice(offset, offset + chunkSize));
      controller.close();
    },
  });
}

async function collect(text: string, chunkSize = 1) {
  const result = [];
  for await (const item of chatEvents(stream(text, chunkSize)))
    result.push(item);
  return result;
}

test("UTF-8 Chinese split at each byte, CRLF, comments and multiline data", async () => {
  const result = await collect(
    ': ping\r\n\r\ndata: {"type":"meta",\r\ndata: "mode":"demo"}\r\n\r\ndata: {"type":"delta","text":"检索练习🌸"}\r\n\r\ndata: {"type":"done"}\r\n\r\n',
  );
  assert.deepEqual(
    result.map((item) => item.type),
    ["meta", "delta", "done"],
  );
  assert.equal(result[1].text, "检索练习🌸");
});

test("multiple events in a network chunk preserve ordering and server errors", async () => {
  const result = await collect(
    'data: {"type":"delta","text":"资料"}\n\ndata: {"type":"error","message":"余额不足"}\n\n',
    1000,
  );
  assert.equal(result[0].text, "资料");
  assert.equal(result[1].message, "余额不足");
});

test("truncation, invalid events and oversized buffers reject", async () => {
  await assert.rejects(
    collect('data: {"type":"delta","text":"截断"}\n\n'),
    /连接中断/,
  );
  await assert.rejects(collect("data: null\n\n"), /格式无效/);
  await assert.rejects(
    collect('data: {"type":"delta","text":3}\n\n'),
    /文字格式无效/,
  );
  await assert.rejects(collect("data: nope\n\n"), SyntaxError);
  await assert.rejects(collect("a".repeat(65537), 4096), /大小限制/);
});

test("consumer cancellation releases the reader", async () => {
  let cancelled = false;
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(
        new TextEncoder().encode('data: {"type":"delta","text":"你好"}\n\n'),
      );
    },
    cancel() {
      cancelled = true;
    },
  });
  for await (const item of chatEvents(body)) {
    assert.equal(item.text, "你好");
    break;
  }
  assert.equal(cancelled, true);
  assert.equal(body.locked, false);
});
