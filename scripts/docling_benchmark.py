"""Compare two real local parsers using original fixtures and isolated processes."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def convert(engine, source, output):
    started = time.perf_counter()
    if engine == "docling":
        from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractOcrOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        options = PdfPipelineOptions(
            artifacts_path=ROOT / "data/docling-models",
            do_ocr=source.name == "original-scan.pdf",
            do_table_structure=True,
            accelerator_options=AcceleratorOptions(num_threads=2, device=AcceleratorDevice.CPU),
            ocr_options=TesseractOcrOptions(
                lang=["chi_sim", "eng"], path=str(ROOT / "data/tessdata"),
                force_full_page_ocr=True, scale=2.5,
            ),
        )
        converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF, InputFormat.PPTX, InputFormat.DOCX],
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
        )

        def parse():
            result = converter.convert(source, max_num_pages=10, max_file_size=10 * 1024 * 1024)
            document = result.document.export_to_dict()
            text = result.document.export_to_markdown()
            return text, document, result.status.value
    else:
        from backend.parsers import parse_document
        from backend.ocr import configured_ocr_provider

        ocr = configured_ocr_provider()

        def parse():
            chunks = parse_document(source.name, source.read_bytes(), ocr=ocr)
            return "\n".join(text for _, text in chunks), {"chunks": chunks}, "success"

    import_setup_seconds = time.perf_counter() - started
    runs = []
    cpu_started = time.process_time()
    for index in range(2):
        began = time.perf_counter()
        text, document, status = parse()
        runs.append({"conversion_seconds": time.perf_counter() - began, "status": status})
        (output / f"pass-{index + 1}.json").write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "extracted.md").write_text(text, encoding="utf-8")
    normalized = "".join(text.split())
    expected = {
        "original.pdf": ["Study methods", "Retrieval practice", "Close the book"],
        "original.docx": ["学习方法", "检索练习", "主动回忆", "合上书复述"],
        "original.pptx": ["学习方法", "检索练习", "Recall", "Read", "回忆", "阅读"],
        "original-scan.pdf": ["学习方法", "检索练习", "主动回忆知识", "Retrieval practice"],
    }
    if source.name == "original-layout.pdf":
        truth = json.loads((source.with_suffix(".expected.json")).read_text(encoding="utf-8"))
        expected[source.name] = truth["headings"] + truth["phrases"] + truth["table_cells"]
    checks = {phrase: "".join(phrase.split()) in normalized for phrase in expected[source.name]}
    summary = {
        "import_setup_seconds": import_setup_seconds,
        "runs": runs, "conversion_cpu_seconds": time.process_time() - cpu_started,
        "characters": len(text), "text_checks": checks,
    }
    if engine == "docling":
        items = document.get("texts", []) + document.get("tables", [])
        summary["source_items"] = [
            {"ref": item["self_ref"], "label": item["label"], "pages": [prov["page_no"] for prov in item.get("prov", [])]}
            for item in items
        ]
        summary["tables"] = [
            {"rows": table["data"]["num_rows"], "columns": table["data"]["num_cols"], "cells": table["data"]["table_cells"]}
            for table in document.get("tables", [])
        ]
    else:
        summary["source_items"] = [location for location, _ in document["chunks"]]
        summary["tables"] = None
    print(json.dumps(summary, ensure_ascii=False), flush=True)


def benchmark():
    import psutil

    directory = ROOT / "test-results" / ("docling-" + uuid4().hex)
    directory.mkdir(parents=True)
    environment = {
        **os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
        "OMP_NUM_THREADS": "2", "OMP_THREAD_LIMIT": "2", "HF_HUB_OFFLINE": "1",
        "HF_HOME": str(ROOT / "data/docling-hf-cache"),
        "OCR_MODE": "tesseract", "OCR_DATA_PATH": str(ROOT / "data/tessdata"),
    }
    interpreters = {
        "lightweight": ROOT / ".venv/Scripts/python.exe",
        "docling": ROOT / "data/docling-env/Scripts/python.exe",
    }
    report = {
        "status": "running", "created_at": datetime.now(timezone.utc).isoformat(),
        "scratch_directory": str(directory), "sample_interval_ms": 10,
        "memory_scope": "Sampled sum of RSS in child process tree, shared pages may be counted more than once",
        "runs_per_process": 2, "ocr_dpi": 180, "cpu_threads": 2,
        "model_source": json.loads((ROOT / "data/docling-models/sources.json").read_text(encoding="utf-8")),
        "results": [],
    }
    report_path = ROOT / "docs/docling-benchmark.json"
    for name in ["original.pdf", "original.pptx", "original.docx", "original-layout.pdf", "original-scan.pdf"]:
        source = ROOT / "tests/samples" / name
        for engine, interpreter in interpreters.items():
            output = directory / (source.name + "-" + engine)
            output.mkdir()
            began = time.perf_counter()
            peak_rss, peak_cpu = 0, 0
            peak_cpu_percent = 0.0
            cpu_window_started = began
            previous_cpu = 0.0
            with (output / "stdout.json").open("wb") as stdout, (output / "stderr.log").open("wb") as stderr:
                child = subprocess.Popen(
                    [str(interpreter), __file__, "--engine", engine, "--source", str(source), "--output", str(output)],
                    cwd=ROOT, env=environment, stdout=stdout, stderr=stderr,
                )
                process = psutil.Process(child.pid)
                timed_out = False
                while child.poll() is None:
                    try:
                        processes = [process] + process.children(recursive=True)
                        peak_rss = max(peak_rss, sum(item.memory_info().rss for item in processes))
                        cpu_total = sum(item.cpu_times().user + item.cpu_times().system for item in processes)
                        peak_cpu = max(peak_cpu, cpu_total)
                        measured_at = time.perf_counter()
                        if measured_at - cpu_window_started >= 0.1:
                            percent = max(0, cpu_total - previous_cpu) / (measured_at - cpu_window_started) * 100
                            peak_cpu_percent = max(peak_cpu_percent, percent)
                            previous_cpu = cpu_total
                            cpu_window_started = measured_at
                        if time.perf_counter() - began > 180:
                            for item in reversed(processes):
                                item.kill()
                            timed_out = True
                            break
                    except psutil.NoSuchProcess:
                        pass
                    time.sleep(0.01)
                child.wait()
            result = {
                "file": name, "engine": engine, "exit_code": child.returncode,
                "timed_out": timed_out, "process_seconds": time.perf_counter() - began,
                "sampled_peak_rss_mib": round(peak_rss / 1024**2, 2),
                "sampled_cpu_seconds": round(peak_cpu, 4),
                "sampled_peak_cpu_percent": round(peak_cpu_percent, 2),
                "cpu_percent_scope": "100% equals one logical core, about 100ms measurement windows",
                "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "output_directory": str(output),
            }
            if child.returncode == 0:
                result.update(json.loads((output / "stdout.json").read_text(encoding="utf-8")))
            else:
                result["error"] = (output / "stderr.log").read_text(encoding="utf-8", errors="replace")[-4000:]
            report["results"].append(result)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({key: result[key] for key in ["file", "engine", "exit_code", "sampled_peak_rss_mib", "process_seconds"]}), flush=True)
    report["status"] = "completed"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    args = argparse.ArgumentParser()
    args.add_argument("--engine", choices=["docling", "lightweight"])
    args.add_argument("--source", type=Path)
    args.add_argument("--output", type=Path)
    parameters = args.parse_args()
    if parameters.engine:
        convert(parameters.engine, parameters.source, parameters.output)
    else:
        benchmark()
