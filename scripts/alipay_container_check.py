"""Boot configured Alipay crypto in the built API image with networking disabled."""
import argparse
import base64
import json
from pathlib import Path
import re
import subprocess
from uuid import uuid4
import rsa
from pyasn1.codec.der.encoder import encode
from pyasn1.type import univ

ROOT = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument("image", help="The API image from a successful isolated compose_check run")
args = parser.parse_args()
if not re.fullmatch(r"galstudycheck[a-f0-9]{12}-api", args.image):
    raise SystemExit("Expected a project-owned Compose API image")
directory = ROOT / "test-results" / ("alipay-container-" + uuid4().hex)
directory.mkdir(parents=True)
app_public, app_private = rsa.newkeys(2048)
provider_public, _ = rsa.newkeys(2048)
(directory / "private.pem").write_bytes(app_private.save_pkcs1())
algorithm = univ.Sequence()
algorithm.setComponentByPosition(0, univ.ObjectIdentifier("1.2.840.113549.1.1.1"))
algorithm.setComponentByPosition(1, univ.Null(""))
spki = univ.Sequence()
spki.setComponentByPosition(0, algorithm)
spki.setComponentByPosition(1, univ.BitString.fromOctetString(provider_public.save_pkcs1("DER")))
b64 = base64.b64encode(encode(spki)).decode()
(directory / "public.pem").write_text("-----BEGIN PUBLIC KEY-----\n" + "\n".join(b64[i:i+64] for i in range(0,len(b64),64)) + "\n-----END PUBLIC KEY-----\n", encoding="ascii")
mount = "/mnt/" + directory.drive[0].lower() + directory.as_posix()[2:]
code = """
import json,os
from types import SimpleNamespace
from uuid import uuid4
from backend import payments
from importlib.metadata import version
p=payments.payment_provider
assert p.mode=='alipay_sandbox'
o=SimpleNamespace(id=str(uuid4()),provider=p.mode,currency='CNY',amount_cents=990,status='pending')
assert p.checkout(o)['url'].startswith('https://openapi.alipaydev.com/gateway.do?')
assert os.getuid()!=0
print(json.dumps({'mode':p.mode,'nonroot':True,'rsa':version('rsa'),'key_loading':'passed','checkout_signing':'passed'}))
"""
command = ["wsl.exe", "-d", "Ubuntu", "--user", "root", "--", "docker", "run", "--rm", "--network", "none",
           "--mount", "type=bind,source=" + mount + ",target=/run/testkeys,readonly"]
for value in ["PAYMENT_PROVIDER=alipay_sandbox", "ALIPAY_APP_ID=2026000000000001", "ALIPAY_SELLER_ID=2088000000000001",
              "ALIPAY_PRIVATE_KEY_PATH=/run/testkeys/private.pem", "ALIPAY_PUBLIC_KEY_PATH=/run/testkeys/public.pem", "APP_ORIGIN=https://example.invalid"]:
    command.extend(["--env", value])
command.extend([args.image, "python", "-c", code])
r = subprocess.run(command, capture_output=True, timeout=60)
lines = r.stdout.decode("utf-8", errors="replace").splitlines()
report = {"status": "failed", "image": args.image, "network": "disabled", "real_transactions": 0,
          "scope": "synthetic read-only key mount and configured provider in actual API container", "exit_code": r.returncode}
if r.returncode == 0:
    report.update(status="passed", container=json.loads(lines[-1]))
else:
    report["stderr_tail"] = r.stderr.decode("utf-8", errors="replace").replace("\x00", "")[-1200:]
(ROOT / "docs/alipay-container-result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=True, indent=2))
if r.returncode:
    raise SystemExit(r.returncode)
