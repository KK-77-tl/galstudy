export function alipayCheckoutUrl(mode: string, value?: string | null): string | null {
  const host = mode === "alipay_sandbox" ? "openapi.alipaydev.com" : mode === "alipay_live" ? "openapi.alipay.com" : null;
  if (!host || !value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname === host && !url.port && !url.username && !url.password && !url.hash && url.pathname === "/gateway.do"
      ? url.href : null;
  } catch { return null; }
}

export function paymentModeLabel(mode: string): string {
  return ({ mock: "Mock 演示", alipay_sandbox: "支付宝沙箱", alipay_live: "支付宝付款" } as Record<string, string>)[mode] ?? "支付环境未启用";
}
