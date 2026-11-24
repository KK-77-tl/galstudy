"""Strict Alipay notification signature and trusted order binding.

The configured provider calls this before active query and order mutation.
"""
import base64
from dataclasses import dataclass
from decimal import Decimal
import re
from urllib.parse import parse_qsl


@dataclass(frozen=True)
class VerifiedAlipayNotice:
    order_id: str
    trade_id: str
    amount_cents: int
    trade_status: str

    @property
    def paid(self):
        return self.trade_status in {"TRADE_SUCCESS", "TRADE_FINISHED"}


def verify_notification(body, public_key, *, app_id, seller_id, order_id, amount_cents):
    """Verify RSA2 and bind the notice to a trusted server-side order snapshot.

    A valid signature alone does not authorize a different application, payee,
    order or amount. No user identifiers or signed raw payload are logged.
    """
    import rsa

    try:
        if not isinstance(body, bytes) or not 1 <= len(body) <= 16384:
            raise ValueError
        if not app_id or not seller_id or not order_id or type(amount_cents) is not int or amount_cents <= 0:
            raise ValueError
        pairs = parse_qsl(body.decode("utf-8", errors="strict"), keep_blank_values=True,
                          strict_parsing=True, encoding="utf-8", errors="strict", max_num_fields=128)
        params = dict(pairs)
        if len(params) != len(pairs):
            raise ValueError
        if params.get("sign_type") != "RSA2" or params.get("charset", "utf-8").lower() != "utf-8":
            raise ValueError
        signature = base64.b64decode(params["sign"], validate=True)
        canonical = "&".join(f"{key}={params[key]}" for key in sorted(params)
                             if key not in {"sign", "sign_type"} and params[key] != "")
        key = rsa.PublicKey.load_pkcs1_openssl_pem(public_key)
        if key.n.bit_length() < 2048 or rsa.verify(canonical.encode("utf-8"), signature, key) != "SHA-256":
            raise ValueError
        if (params.get("app_id") != app_id or params.get("seller_id") != seller_id
                or params.get("out_trade_no") != order_id
                or params.get("auth_app_id", app_id) != app_id):
            raise ValueError
        amount = params.get("total_amount", "")
        if not re.fullmatch(r"(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,2})?", amount):
            raise ValueError
        cents = int(Decimal(amount) * 100)
        if cents != amount_cents:
            raise ValueError
        trade_id = params.get("trade_no", "")
        status = params.get("trade_status", "")
        if not re.fullmatch(r"[0-9]{1,64}", trade_id) or status not in {
            "WAIT_BUYER_PAY", "TRADE_CLOSED", "TRADE_SUCCESS", "TRADE_FINISHED"
        }:
            raise ValueError
        return VerifiedAlipayNotice(order_id, trade_id, cents, status)
    except Exception as error:
        raise ValueError("支付宝通知验签或订单核对失败") from error
