"""Verify size boundaries through the real Next.js proxy and private API."""

import hashlib
import json
import os
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import httpx
from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:3000")
limit = 10 * 1024 * 1024
subject_length = limit - 1000
for _ in range(3):
    writer = PdfWriter()
    for page in PdfReader(ROOT / "tests/samples/original.pdf").pages:
        writer.add_page(page)
    writer.add_metadata({"/Subject": "a" * subject_length})
    output = BytesIO()
    writer.write(output)
    pdf = output.getvalue()
    subject_length += limit - len(pdf)
assert len(pdf) == limit

with httpx.Client(base_url=BASE_URL, timeout=60, trust_env=False) as client:
    client.post(
        "/api/auth/register",
        json={
            "email": f"limits-{uuid4().hex}@example.com",
            "password": "GalStudy-size-probe-2026",
        },
    ).raise_for_status()
    cid = client.post("/api/courses", json={"title": "请求边界验收"}).json()["id"]
    path = f"/api/courses/{cid}/files"
    accepted = client.post(
        path, files={"file": ("exact-limit.pdf", pdf, "application/pdf")}
    )
    assert accepted.status_code == 202, accepted.text
    fid = accepted.json()["id"]
    downloaded = client.get(path + "/" + fid)
    downloaded.raise_for_status()
    assert hashlib.sha256(downloaded.content).digest() == hashlib.sha256(pdf).digest()
    removed = client.delete(path + "/" + fid)
    assert removed.status_code == 200, removed.text
    oversized_file = client.post(
        path, files={"file": ("too-large.pdf", pdf + b"x", "application/pdf")}
    )
    assert oversized_file.status_code == 422, oversized_file.text
    oversized_body = client.post(path, content=b"x" * (11 * 1024 * 1024 + 1))
    assert oversized_body.status_code == 413, oversized_body.text
    oversized_json = client.post(
        "/api/courses",
        content=b"x" * (64 * 1024 + 1),
        headers={"Content-Type": "application/json"},
    )
    assert oversized_json.status_code == 413, oversized_json.text
    report = {
        "through": "Next.js /api rewrite to private API",
        "exact_file_limit_bytes": len(pdf),
        "accepted_status": accepted.status_code,
        "download_sha256_matches": True,
        "delete_queued_or_processing_source": removed.status_code,
        "one_byte_over_file_limit": oversized_file.status_code,
        "over_upload_request_limit": oversized_body.status_code,
        "over_json_request_limit": oversized_json.status_code,
    }
    (ROOT / "docs/request-limit-probe.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
