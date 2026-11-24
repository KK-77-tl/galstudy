import importlib.util
import os
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from backend import main
from backend.ocr import TesseractOCRProvider, configured_ocr_provider, ocr_ready
from backend.providers import OCRUnavailable
from backend.parsers import parse_document
from scripts.make_samples import make_samples

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def tmp_path():
    directory = ROOT / "test-results" / ("ocr-unit-" + uuid4().hex)
    directory.mkdir(parents=True)
    return directory


@pytest.mark.parametrize(
    "kwargs",
    [{"languages": "eng;run"}, {"dpi": 600}, {"max_pixels": 100}, {"max_pages": 0}],
)
def test_ocr_configuration_limits(tmp_path, kwargs):
    with pytest.raises(OCRUnavailable):
        TesseractOCRProvider(tmp_path, **kwargs)


def test_missing_model_and_page_budget_are_clear(tmp_path):
    model = TesseractOCRProvider(tmp_path)
    with pytest.raises(OCRUnavailable, match="语言模型缺失"):
        model.extract_pdf_page(b"pdf", 1)
    model.pages = model.max_pages
    with pytest.raises(OCRUnavailable, match="扫描页超过"):
        model.extract_pdf_page(b"pdf", 1)


def test_ocr_mode_and_readiness(monkeypatch, tmp_path):
    monkeypatch.setenv("OCR_MODE", "disabled")
    assert not ocr_ready()
    monkeypatch.setenv("OCR_MODE", "unknown")
    with pytest.raises(OCRUnavailable, match="模式"):
        configured_ocr_provider()
    monkeypatch.setenv("OCR_MODE", "tesseract")
    monkeypatch.setenv("OCR_DATA_PATH", str(tmp_path))
    assert not ocr_ready()
    monkeypatch.setenv("OCR_DPI", "invalid")
    with pytest.raises(OCRUnavailable, match="配置"):
        configured_ocr_provider()


def test_text_pdf_skips_ocr_and_scan_has_marker(tmp_path):
    samples = make_samples(tmp_path)

    class OCR:
        calls = 0

        def extract_pdf_page(self, data, page_number):
            self.calls += 1
            return "original recognized text"

    model = OCR()
    parse_document("original.pdf", (samples / "original.pdf").read_bytes(), model)
    assert model.calls == 0
    chunks = parse_document("scan.pdf", (samples / "no-text.pdf").read_bytes(), model)
    assert chunks == [("第 1 页 · OCR", "original recognized text")]


HAS_OCR = (
    all(importlib.util.find_spec(name) for name in ("tesserocr", "pypdfium2"))
    and (ROOT / "data/tessdata/chi_sim.traineddata").exists()
    and (ROOT / "tests/samples/original-scan.pdf").exists()
)


@pytest.mark.skipif(
    not HAS_OCR,
    reason="Optional local OCR dependencies/models and scan fixture required",
)
def test_real_local_ocr_and_pixel_limit():
    data = (ROOT / "tests/samples/original-scan.pdf").read_bytes()
    model = TesseractOCRProvider(ROOT / "data/tessdata")
    chunks = parse_document("original-scan.pdf", data, model)
    text = "".join(chunks[0][1].split())
    assert "检索练习" in text and "Retrievalpractice" in text
    with pytest.raises(OCRUnavailable, match="像素"):
        TesseractOCRProvider(
            ROOT / "data/tessdata", max_pixels=1_000_000
        ).extract_pdf_page(data, 1)


@pytest.mark.skipif(not HAS_OCR, reason="Optional local OCR components required")
def test_scan_upload_worker_and_account_isolation(monkeypatch):
    monkeypatch.setenv("OCR_MODE", "tesseract")
    monkeypatch.setenv("OCR_DATA_PATH", str(ROOT / "data/tessdata"))
    with TestClient(main.app) as a, TestClient(main.app) as b:
        for client in (a, b):
            client.post(
                "/api/auth/register",
                json={
                    "email": uuid4().hex + "@example.com",
                    "password": "ocr-test-password",
                },
            )
        cid = a.post("/api/courses", json={"title": "扫描教材"}).json()["id"]
        assert a.get(f"/api/courses/{cid}").json()["ocr_enabled"]
        fid = a.post(
            f"/api/courses/{cid}/files",
            files={
                "file": (
                    "original-scan.pdf",
                    (ROOT / "tests/samples/original-scan.pdf").read_bytes(),
                )
            },
        ).json()["id"]
        from test_acceptance import finish_parse

        assert finish_parse(a, cid, fid)["status"] == "ready"
        detail = a.get(f"/api/courses/{cid}").json()
        assert "OCR" in detail["points"][0]["location"]
        assert "检索" in detail["points"][0]["source"]
        assert b.get(f"/api/courses/{cid}/files/{fid}").status_code == 404
