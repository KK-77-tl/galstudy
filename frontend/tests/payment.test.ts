import { test } from "node:test";
import assert from "node:assert/strict";
import { alipayCheckoutUrl, paymentModeLabel } from "../lib/payment.ts";

test("payment redirects stay on the matching HTTPS Alipay gateway", () => {
  const sandbox = "https://openapi.alipaydev.com/gateway.do?sign=test";
  assert.equal(alipayCheckoutUrl("alipay_sandbox", sandbox), sandbox);
  assert.equal(alipayCheckoutUrl("alipay_live", "https://openapi.alipay.com/gateway.do?x=1"), "https://openapi.alipay.com/gateway.do?x=1");
  for (const value of [sandbox, "javascript:alert(1)", "https://openapi.alipay.com.evil.invalid/gateway.do", "http://openapi.alipay.com/gateway.do", "https://user@openapi.alipay.com/gateway.do", "https://openapi.alipay.com:8443/gateway.do", "https://openapi.alipay.com/other", "https://openapi.alipay.com/gateway.do#fragment"]) {
    assert.equal(alipayCheckoutUrl("alipay_live", value), null);
  }
  assert.equal(alipayCheckoutUrl("mock", sandbox), null);
  assert.equal(alipayCheckoutUrl("unknown", sandbox), null);
});

test("payment labels distinguish demo, sandbox and live modes", () => {
  assert.equal(paymentModeLabel("mock"), "Mock 演示");
  assert.equal(paymentModeLabel("alipay_sandbox"), "支付宝沙箱");
  assert.equal(paymentModeLabel("alipay_live"), "支付宝付款");
  assert.equal(paymentModeLabel("unexpected"), "支付环境未启用");
});
