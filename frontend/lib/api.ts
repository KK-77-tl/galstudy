let sessionVersion = 0;

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  if (/^\/auth\/(login|register|logout)$/.test(path)) sessionVersion += 1;
  const version = sessionVersion;
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const response = await fetch("/api" + path, { ...options, headers });
  const data = await response.json();
  if (version !== sessionVersion)
    throw new DOMException("账号会话已切换", "AbortError");
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "请求失败，请检查输入后重试",
    );
  return data;
}
