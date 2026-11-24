"""Small local acceptance sample. Creates one synthetic account and a 5 MiB PDF."""

import json
import os
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import httpx
import psutil
from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).resolve().parent.parent
API_URL = os.getenv("PERF_API_URL", "http://127.0.0.1:8000")
WEB_URL = os.getenv("E2E_BASE_URL", "http://localhost:3000")


def summary(values):
    ordered = sorted(values)
    return {
        "requests": len(values),
        "p50_ms": round(statistics.median(values), 2),
        "p95_ms": round(ordered[max(0, int(len(ordered) * 0.95) - 1)], 2),
        "max_ms": round(max(values), 2),
    }


def main():
    api = httpx.Client(base_url=API_URL, timeout=30, trust_env=False)
    api.post(
        "/api/auth/register",
        json={
            "email": f"perf-{uuid4().hex}@example.com",
            "password": "GalStudy-performance-2026",
        },
    ).raise_for_status()
    course = api.post("/api/courses", json={"title": "本地性能验收 · 原创样本"}).json()[
        "id"
    ]
    writer = PdfWriter()
    for page in PdfReader(ROOT / "tests/samples/original.pdf").pages:
        writer.add_page(page)
    writer.add_metadata({"/Subject": "a" * (5 * 1024 * 1024)})
    output = BytesIO()
    writer.write(output)
    uploaded = api.post(
        f"/api/courses/{course}/files",
        files={
            "file": ("performance-original.pdf", output.getvalue(), "application/pdf")
        },
    )
    uploaded.raise_for_status()
    deadline = time.monotonic() + 50
    while time.monotonic() < deadline:
        response = api.get(f"/api/courses/{course}")
        response.raise_for_status()
        state = response.json()["files"][0]
        if state["status"] == "ready":
            break
        if state["status"] == "failed":
            raise RuntimeError(state["error"])
        time.sleep(0.1)
    else:
        raise RuntimeError("Parse timeout")
    processes = []
    for process in psutil.process_iter(["cmdline"]):
        command = process.info["cmdline"] or []
        if "uvicorn" in command and "backend.main:app" in command:
            processes.append(process)
    samples = []
    stop = threading.Event()

    def sample():
        while not stop.is_set():
            samples.append(
                sum(process.memory_info().rss for process in processes) / 1024**2
            )
            stop.wait(0.01)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    try:

        def request(_):
            started = time.perf_counter()
            response = api.get(f"/api/courses/{course}")
            response.raise_for_status()
            assert len(response.content) < 50000
            return (time.perf_counter() - started) * 1000

        sequential = [request(index) for index in range(30)]
        with ThreadPoolExecutor(max_workers=8) as executor:
            concurrent = list(executor.map(request, range(80)))
        with httpx.Client(base_url=WEB_URL, timeout=30, trust_env=False) as web:
            html_times = []
            for _ in range(10):
                started = time.perf_counter()
                web.get("/study").raise_for_status()
                html_times.append((time.perf_counter() - started) * 1000)
    finally:
        stop.set()
        sampler.join()
    report = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "environment": "Windows local production Next.js, SQLite, one Uvicorn worker",
        "uploaded_pdf_bytes": len(output.getvalue()),
        "course_response_bytes": len(response.content),
        "course_sequential": summary(sequential),
        "course_8_concurrent": summary(concurrent),
        "web_html_sequential": summary(html_times),
        "api_sampled_rss_mib": {
            "process_count": len(processes),
            "minimum": round(min(samples), 2),
            "peak": round(max(samples), 2),
        },
        "scope": "Local warm metadata and HTML requests only. Excludes WAN, browser paint, cloud inference and GPU. No hosting capacity or monthly cost extrapolation.",
    }
    (ROOT / "docs/performance-result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
