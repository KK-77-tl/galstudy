"""Bounded RSA2 transport for direct-merchant Alipay page pay and refunds.

This component is not selected by the running Mock payment provider. Callers
must bind verified responses to their order and entitlement transactions.
"""
import asyncio
import base64
from datetime import datetime, timezone, timedelta
import json
import re
from urllib.parse import urlencode, urlparse
from uuid import UUID

import httpx

MAX_RESPONSE = 128 * 1024


class AlipayGatewayError(Exception):
    pass


class AlipayOutcomeUnknown(AlipayGatewayError):
    """A request may have reached the provider; query before retrying a refund."""


def _order_id(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("订单号必须是应用生成的UUID")
    return value


def _amount(cents):
    if type(cents) is not int or not 1 <= cents <= 1000000:
        raise ValueError("金额超出角色包支持范围")
    return f"{cents // 100}.{cents % 100:02d}"


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _response_part(text, expected):
    # Verify the exact signed slice, preserving escapes and whitespace.
    def nonfinite(_):
        raise ValueError("Non-finite JSON number")
    decoder = json.JSONDecoder(object_pairs_hook=_unique, parse_constant=nonfinite)
    obj = decoder.decode(text)
    if not isinstance(obj, dict) or not isinstance(obj.get(expected), dict):
        raise ValueError("Missing response object")
    index = text.index("{") + 1
    while True:
        while text[index].isspace():
            index += 1
        if text[index] == "}":
            break
        key, index = decoder.raw_decode(text, index)
        while text[index].isspace():
            index += 1
        if text[index] != ":":
            raise ValueError("Invalid JSON field")
        index += 1
        while text[index].isspace():
            index += 1
        begin = index
        _, index = decoder.raw_decode(text, index)
        if key == expected:
            return obj, text[begin:index].encode("utf-8")
        while text[index].isspace():
            index += 1
        if text[index] == ",":
            index += 1
        else:
            break
    raise ValueError("Missing response slice")


class AlipayGateway:
    def __init__(self, app_id, private_key, alipay_public_key, *, sandbox=True, transport=None, timeout=20):
        import rsa
        if not re.fullmatch(r"[0-9]{16,32}", app_id) or type(sandbox) is not bool or not 1 <= timeout <= 30:
            raise ValueError("支付宝应用或环境配置无效")
        self.app_id = app_id
        self.private = rsa.PrivateKey.load_pkcs1(private_key)
        self.public = rsa.PublicKey.load_pkcs1_openssl_pem(alipay_public_key)
        if min(self.private.n.bit_length(), self.public.n.bit_length()) < 2048:
            raise ValueError("支付宝需要至少2048位RSA密钥")
        self.gateway = "https://openapi.alipaydev.com/gateway.do" if sandbox else "https://openapi.alipay.com/gateway.do"
        self.transport = transport
        self.timeout = timeout

    def _params(self, method, biz, **extra):
        import rsa
        params = {
            "app_id": self.app_id, "method": method, "format": "JSON", "charset": "utf-8", "sign_type": "RSA2",
            "timestamp": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0", "biz_content": json.dumps(biz, ensure_ascii=False, separators=(",", ":")), **extra,
        }
        content = "&".join(f"{key}={params[key]}" for key in sorted(params)).encode("utf-8")
        params["sign"] = base64.b64encode(rsa.sign(content, self.private, "SHA-256")).decode()
        return params

    def checkout_url(self, order_id, amount_cents, origin):
        url = urlparse(origin)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}:
            raise ValueError("收款站点须为服务端配置的HTTPS源")
        origin = origin.rstrip("/")
        params = self._params("alipay.trade.page.pay", {
            "out_trade_no": _order_id(order_id), "total_amount": _amount(amount_cents),
            "subject": "专属陪学角色静态包", "product_code": "FAST_INSTANT_TRADE_PAY",
        }, notify_url=origin + "/api/workshop/payments/alipay/notify", return_url=origin + "/study")
        return self.gateway + "?" + urlencode(params)

    async def _request(self, method, biz):
        try:
            return await asyncio.wait_for(self._exchange(method, biz), timeout=self.timeout)
        except (TimeoutError, httpx.TransportError) as error:
            raise AlipayOutcomeUnknown("支付请求结果未知，请先查询交易或退款状态。") from error

    async def _exchange(self, method, biz):
        import rsa
        try:
            async with httpx.AsyncClient(transport=self.transport, follow_redirects=False,
                                         timeout=httpx.Timeout(self.timeout, connect=min(5, self.timeout))) as client:
                async with client.stream("POST", self.gateway, data=self._params(method, biz),
                                         headers={"User-Agent": "GalStudy/0.1"}) as response:
                    if response.status_code != 200:
                        raise AlipayOutcomeUnknown("支付接口未确认处理结果，请先查询状态。")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(body) + len(chunk) > MAX_RESPONSE:
                            raise AlipayOutcomeUnknown("支付响应超出限制，须查询处理结果")
                        body.extend(chunk)
            name = method.replace(".", "_") + "_response"
            envelope, signed = _response_part(body.decode("utf-8", errors="strict"), name)
            if envelope.get("sign_type", "RSA2") != "RSA2":
                raise ValueError("Unsupported signature")
            if rsa.verify(signed, base64.b64decode(envelope["sign"], validate=True), self.public) != "SHA-256":
                raise ValueError("Unsupported hash")
            data = envelope[name]
            if data.get("code") != "10000":
                raise AlipayGatewayError("支付宝未确认操作成功")
            return data
        except (ValueError, TypeError, KeyError, IndexError, RecursionError, rsa.VerificationError) as error:
            raise AlipayOutcomeUnknown("支付宝响应格式或RSA2验签失败，须查询处理结果") from error

    async def query(self, order_id):
        return await self._request("alipay.trade.query", {"out_trade_no": _order_id(order_id)})

    async def refund(self, order_id, amount_cents, refund_id):
        return await self._request("alipay.trade.refund", {
            "out_trade_no": _order_id(order_id), "out_request_no": _order_id(refund_id),
            "refund_amount": _amount(amount_cents),
        })

    async def query_refund(self, order_id, refund_id):
        return await self._request("alipay.trade.fastpay.refund.query", {
            "out_trade_no": _order_id(order_id), "out_request_no": _order_id(refund_id),
        })
