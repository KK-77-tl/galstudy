"""Official SDK/RSA2 offline contract checks using ephemeral synthetic keys only."""
import base64
from importlib.metadata import version
import json
from pathlib import Path
import sys
from urllib.parse import parse_qsl, urlencode, urlparse
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from Crypto.PublicKey import RSA
import rsa
from alipay.aop.api.AlipayClientConfig import AlipayClientConfig
from alipay.aop.api.DefaultAlipayClient import DefaultAlipayClient
from alipay.aop.api.request.AlipayTradePagePayRequest import AlipayTradePagePayRequest
from alipay.aop.api.domain.AlipayTradePagePayModel import AlipayTradePagePayModel
from alipay.aop.api.util.SignatureUtils import sign_with_rsa2, verify_with_rsa
from backend.alipay_protocol import verify_notification

key = RSA.generate(2048)
private = key.export_key(pkcs=1).decode()
public = key.public_key().export_key().decode()
app_key = RSA.generate(2048)
app_private = app_key.export_key(pkcs=1).decode()
app_public = app_key.public_key().export_key().decode()
oid = str(uuid4())
report = {"status": "running", "sdk": version("alipay-sdk-python"), "network_calls": 0,
          "real_transactions": 0, "keys": "ephemeral synthetic; not saved", "checks": []}

def check(name, condition):
    report["checks"].append({"name": name, "passed": bool(condition)})
    if not condition:
        raise AssertionError(name)

def canonical(p):
    return "&".join(f"{k}={p[k]}" for k in sorted(p) if k not in {"sign", "sign_type"} and p[k] != "")

def signed(p, algorithm="SHA-256"):
    p = dict(p)
    if algorithm == "SHA-256":
        p["sign"] = sign_with_rsa2(private, canonical(p), "utf-8")
    else:
        p["sign"] = base64.b64encode(rsa.sign(canonical(p).encode(), rsa.PrivateKey.load_pkcs1(private), algorithm)).decode()
    return urlencode(p).encode()

expected = {"app_id": "2026000000000001", "seller_id": "2088000000000001", "order_id": oid, "amount_cents": 990}
params = {"app_id": expected["app_id"], "seller_id": expected["seller_id"], "out_trade_no": oid,
          "total_amount": "9.90", "trade_no": "20260000000000000001", "trade_status": "TRADE_SUCCESS",
          "sign_type": "RSA2", "charset": "utf-8", "subject": "原创角色包 & 学习"}
try:
    config = AlipayClientConfig(sandbox_debug=True)
    config.app_id, config.app_private_key, config.alipay_public_key = expected["app_id"], app_private, public
    config.sign_type = "RSA2"
    client = DefaultAlipayClient(config, logger=None)
    model = AlipayTradePagePayModel()
    model.out_trade_no, model.total_amount = oid, "9.90"
    model.subject, model.product_code = "原创角色包", "FAST_INSTANT_TRADE_PAY"
    request = AlipayTradePagePayRequest(biz_model=model)
    request.notify_url = "https://example.invalid/api/workshop/payments/alipay/notify"
    checkout = client.page_execute(request, "GET")
    url = urlparse(checkout)
    data = dict(parse_qsl(url.query))
    signature = base64.b64decode(data.pop("sign"))
    # Request signatures include sign_type; notification signatures exclude it.
    content = "&".join(f"{k}={data[k]}" for k in sorted(data)).encode()
    check("official_sdk_checkout_rsa2", rsa.verify(content, signature, rsa.PublicKey.load_pkcs1_openssl_pem(app_public)) == "SHA-256")
    check("sandbox_gateway", url.hostname == "openapi.alipaydev.com")
    biz = json.loads(data["biz_content"])
    check("server_order_amount", biz["total_amount"] == "9.90" and biz["out_trade_no"] == oid)
    check("valid_rsa2_notification", verify_notification(signed(params), public, **expected).paid)
    for label, changed in [
        ("wrong_app", {"app_id": "2026000000000002"}), ("wrong_seller", {"seller_id": "2088000000000002"}),
        ("wrong_order", {"out_trade_no": str(uuid4())}), ("wrong_amount", {"total_amount": "0.01"}),
        ("float_exponent", {"total_amount": "9.9e0"}), ("excess_precision", {"total_amount": "9.900"}),
    ]:
        try:
            verify_notification(signed({**params, **changed}), public, **expected)
            rejected = False
        except ValueError:
            rejected = True
        check(label + "_rejected_even_when_signed", rejected)
    wrong_signer = {**params, "sign": sign_with_rsa2(app_private, canonical(params), "utf-8")}
    for label, body in [("merchant_key_cannot_impersonate_alipay", urlencode(wrong_signer).encode()),
                        ("duplicate_field", signed(params) + b"&total_amount=9.90"),
                        ("tampered", signed(params).replace(b"9.90", b"9.91")),
                        ("sha1_labelled_rsa2", signed(params, "SHA-1"))]:
        try:
            verify_notification(body, public, **expected)
            rejected = False
        except ValueError:
            rejected = True
        check(label + "_rejected", rejected)
    check("closed_notice_never_paid", not verify_notification(signed({**params, "trade_status": "TRADE_CLOSED"}), public, **expected).paid)
    sha1 = dict(parse_qsl(signed(params, "SHA-1").decode()))
    report["sdk_generic_verifier_accepts_sha1"] = verify_with_rsa(public, canonical(sha1).encode(), sha1["sign"])
    report["status"] = "passed"
finally:
    (ROOT / "docs/alipay-contract-result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))
