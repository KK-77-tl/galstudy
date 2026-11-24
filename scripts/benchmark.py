"""Measure lightweight parser process CPU, elapsed time, and sampled RSS."""

import json
import subprocess
import sys
import time
from pathlib import Path
import psutil

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.make_samples import make_samples

if "--child" in sys.argv:
    from backend.parsers import parse_document

    path = Path(sys.argv[-1])
    started = time.perf_counter()
    chunks = parse_document(path.name, path.read_bytes())
    print(
        json.dumps(
            {
                "parse_seconds": time.perf_counter() - started,
                "chunks": len(chunks),
                "characters": sum(len(t) for _, t in chunks),
            }
        ),
        flush=True,
    )
else:
    directory = make_samples()
    results = []
    for extension in ["pdf", "pptx", "docx"]:
        child = subprocess.Popen(
            [
                sys.executable,
                __file__,
                "--child",
                str(directory / ("original." + extension)),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        process = psutil.Process(child.pid)
        peak_rss = 0
        cpu_seconds = 0
        started = time.perf_counter()
        while child.poll() is None:
            try:
                peak_rss = max(peak_rss, process.memory_info().rss)
                cpu = process.cpu_times()
                cpu_seconds = cpu.user + cpu.system
            except psutil.NoSuchProcess:
                break
            time.sleep(0.01)
        stdout, stderr = child.communicate()
        if child.returncode:
            raise RuntimeError(stderr)
        results.append(
            {
                "file": "original." + extension,
                "process_seconds": time.perf_counter() - started,
                "sampled_peak_rss_mib": round(peak_rss / 1024**2, 2),
                "cpu_seconds": cpu_seconds,
                **json.loads(stdout),
            }
        )
    report = {
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "logical_cpu": psutil.cpu_count(),
        "ram_gib": round(psutil.virtual_memory().total / 1024**3, 1),
        "sample_interval_ms": 10,
        "runs_per_file": 1,
        "docling": "未测试，未安装 Docling 或其模型",
        "results": results,
    }
    Path("docs/parser-benchmark.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
