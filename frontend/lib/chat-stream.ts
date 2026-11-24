export type StreamEvent = {
  type: "meta" | "delta" | "done" | "error";
  text?: string;
  message?: string;
  mode?: string;
  references?: {
    point_id: string;
    file: string;
    location: string;
    quote: string;
  }[];
  usage?: {
    remaining_requests: number;
    remaining_reserved_tokens: number;
    warning: boolean;
  };
};

export async function* chatEvents(body: ReadableStream<Uint8Array>) {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += done
        ? decoder.decode()
        : decoder.decode(value, { stream: true });
      let boundary = /\r?\n\r?\n/.exec(buffer);
      while (boundary) {
        const block = buffer.slice(0, boundary.index);
        buffer = buffer.slice(boundary.index + boundary[0].length);
        if (block.length > 65536) throw new Error("回复事件超过大小限制");
        const data = block
          .split(/\r?\n/)
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).replace(/^ /, ""))
          .join("\n");
        if (data) {
          const item: StreamEvent = JSON.parse(data);
          if (!item || !["meta", "delta", "done", "error"].includes(item.type))
            throw new Error("回复事件格式无效");
          if (item.type === "delta" && typeof item.text !== "string")
            throw new Error("回复文字格式无效");
          yield item;
          if (item.type === "done" || item.type === "error") return;
        }
        boundary = /\r?\n\r?\n/.exec(buffer);
      }
      if (buffer.length > 65536) throw new Error("回复事件超过大小限制");
      if (done) throw new Error("连接中断，请刷新会话查看保存状态");
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
