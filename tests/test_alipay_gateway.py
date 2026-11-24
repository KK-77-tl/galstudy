import asyncio
import base64
import json
from urllib.parse import parse_qsl, urlparse
from uuid import uuid4
import httpx
import pytest

rsa = pytest.importorskip("rsa", reason="Install requirements-alipay.txt for payment adapter checks")
from backend.alipay_gateway import AlipayGateway, AlipayGatewayError, AlipayOutcomeUnknown


@pytest.fixture(scope="module")
def keys():
    app_pub, app_priv = rsa.newkeys(2048)
    provider_pub, provider_priv = rsa.newkeys(2048)
    # PKCS#8/SPKI public form without adding a second cryptography dependency.
    from pyasn1.codec.der.encoder import encode
    from pyasn1.type import univ
    algorithm = univ.Sequence()
    algorithm.setComponentByPosition(0, univ.ObjectIdentifier("1.2.840.113549.1.1.1"))
    algorithm.setComponentByPosition(1, univ.Null(""))
    spki = univ.Sequence()
    spki.setComponentByPosition(0, algorithm)
    spki.setComponentByPosition(1, univ.BitString.fromOctetString(provider_pub.save_pkcs1("DER")))
    encoded = base64.b64encode(encode(spki)).decode()
    pem = "-----BEGIN PUBLIC KEY-----\n" + "\n".join(encoded[i:i+64] for i in range(0, len(encoded), 64)) + "\n-----END PUBLIC KEY-----"
    return app_pub, app_priv, provider_priv, pem


def gateway(keys, handler, **kwargs):
    return AlipayGateway("2026000000000001", keys[1].save_pkcs1(), keys[3],
                         transport=httpx.MockTransport(handler), **kwargs)


def envelope(keys, method, raw, algorithm="SHA-256"):
    sign = base64.b64encode(rsa.sign(raw.encode(), keys[2], algorithm)).decode()
    return '{"' + method.replace(".", "_") + '_response":' + raw + ',"sign":' + json.dumps(sign) + '}'


def test_checkout_price_signature_and_gateway_are_bound(keys):
    g = gateway(keys, lambda _: pytest.fail("Checkout must not perform network I/O"))
    oid = str(uuid4())
    url = urlparse(g.checkout_url(oid, 990, "https://example.invalid"))
    params = dict(parse_qsl(url.query))
    signature = base64.b64decode(params.pop("sign"))
    text = "&".join(f"{k}={params[k]}" for k in sorted(params)).encode()
    assert rsa.verify(text, signature, keys[0]) == "SHA-256"
    assert url.hostname == "openapi.alipaydev.com"
    assert json.loads(params["biz_content"])["total_amount"] == "9.90"
    for amount in [True, 0, -1, 1.1, 1000001]:
        with pytest.raises(ValueError):
            g.checkout_url(oid, amount, "https://example.invalid")
    with pytest.raises(ValueError):
        g.checkout_url(oid, 990, "https://example.invalid/?notify=https://attacker.invalid")


def test_signed_raw_response_preserves_escapes_and_whitespace(keys):
    raw = '{ "code" : "10000", "memo":"escaped \\"quote\\" and { braces }", "out_trade_no":"original" }'
    def handler(request):
        params = dict(parse_qsl(request.content.decode()))
        assert params["method"] == "alipay.trade.query"
        return httpx.Response(200, text=envelope(keys, "alipay.trade.query", raw))
    result = asyncio.run(gateway(keys, handler).query(str(uuid4())))
    assert result["code"] == "10000" and "{ braces }" in result["memo"]


@pytest.mark.parametrize("case", ["bad_signature", "sha1", "duplicate", "oversize", "redirect", "nonfinite"])
def test_untrusted_responses_cannot_confirm_payment(keys, case):
    raw = '{"code":"10000"}'
    text = envelope(keys, "alipay.trade.query", raw, "SHA-1" if case == "sha1" else "SHA-256")
    if case == "bad_signature":
        text = text.replace("10000", "10001")
    if case == "duplicate":
        text = text.replace('{"alipay', '{"sign":"duplicate","alipay')
    if case == "oversize":
        text = " " * (128 * 1024 + 1)
    if case == "nonfinite":
        text = envelope(keys, "alipay.trade.query", '{"code":"10000","amount":NaN}')
    def handler(_):
        return httpx.Response(302, headers={"Location": "https://attacker.invalid"}) if case == "redirect" else httpx.Response(200, text=text)
    with pytest.raises(AlipayGatewayError):
        asyncio.run(gateway(keys, handler).query(str(uuid4())))


def test_refund_timeout_is_unknown_and_never_automatically_retried(keys):
    calls = []
    async def handler(request):
        calls.append(request)
        await asyncio.sleep(0.05)
        raise AssertionError("Deadline should cancel request")
    g = gateway(keys, handler)
    g.timeout = 0.01
    with pytest.raises(AlipayOutcomeUnknown):
        asyncio.run(g.refund(str(uuid4()), 990, str(uuid4())))
    assert len(calls) == 1


def test_refund_query_reuses_fixed_request_identifier(keys):
    oid, rid = str(uuid4()), str(uuid4())
    seen = []
    def handler(request):
        params = dict(parse_qsl(request.content.decode()))
        biz = json.loads(params["biz_content"])
        seen.append((params["method"], biz))
        return httpx.Response(200, text=envelope(keys, params["method"], '{"code":"10000"}'))
    g = gateway(keys, handler)
    asyncio.run(g.refund(oid, 990, rid))
    asyncio.run(g.query_refund(oid, rid))
    assert [item[1]["out_request_no"] for item in seen] == [rid, rid]
    assert seen[0][1]["refund_amount"] == "9.90"
