"""Optional local OCR. The parser subprocess supplies the outer hard timeout."""

import math
import importlib.util
import os
from pathlib import Path
import re
import threading
from .providers import OCRUnavailable, UnavailableOCRProvider

PDFIUM_LOCK = threading.Lock()


class TesseractOCRProvider:
    mode = "tesseract"

    def __init__(
        self,
        data_path,
        languages="chi_sim+eng",
        dpi=180,
        max_pixels=8_000_000,
        max_pages=10,
    ):
        self.data_path = Path(data_path)
        self.languages = languages
        self.dpi = dpi
        self.max_pixels = max_pixels
        self.max_pages = max_pages
        self.pages = 0
        if not re.fullmatch(r"[a-z_]+(?:\+[a-z_]+)*", languages):
            raise OCRUnavailable("OCR语言配置无效，请管理员核查。")
        if (
            not 72 <= dpi <= 300
            or not 1_000_000 <= max_pixels <= 16_000_000
            or not 1 <= max_pages <= 100
        ):
            raise OCRUnavailable("OCR资源配置超出支持范围。")

    def extract_pdf_page(self, data, page_number):
        if self.pages >= self.max_pages:
            raise OCRUnavailable(f"扫描页超过{self.max_pages}页OCR限制，请拆分文件。")
        for language in self.languages.split("+"):
            if not (self.data_path / (language + ".traineddata")).is_file():
                raise OCRUnavailable("OCR语言模型缺失，请管理员核查服务端配置。")
        try:
            import pypdfium2 as pdfium
            from tesserocr import PyTessBaseAPI, OEM, PSM
        except (ImportError, OSError) as error:
            raise OCRUnavailable(
                "OCR组件未安装或无法加载，请安装可选OCR依赖。"
            ) from error
        self.pages += 1
        try:
            # PDFium calls must be serialized even when different documents are used.
            with PDFIUM_LOCK, pdfium.PdfDocument(data) as document:
                if not 1 <= page_number <= len(document):
                    raise OCRUnavailable("OCR页码无效。")
                page = document[page_number - 1]
                width, height = page.get_size()
                scale = self.dpi / 72
                if width <= 0 or height <= 0 or not math.isfinite(width * height):
                    raise OCRUnavailable("PDF页面尺寸无效。")
                if (
                    math.ceil(width * scale) * math.ceil(height * scale)
                    > self.max_pixels
                ):
                    raise OCRUnavailable("扫描页像素超过OCR限制，请缩小页面后重试。")
                bitmap = page.render(scale=scale)
                try:
                    image = bitmap.to_pil().convert("RGB")
                finally:
                    bitmap.close()
                    page.close()
            try:
                with PyTessBaseAPI(
                    path=str(self.data_path),
                    lang=self.languages,
                    oem=OEM.LSTM_ONLY,
                    psm=PSM.AUTO,
                ) as recognizer:
                    recognizer.SetImage(image)
                    text = recognizer.GetUTF8Text()
            finally:
                image.close()
            if len(text) > 300_000:
                raise OCRUnavailable("OCR文字超过30万字限制，请拆分文件。")
            return text.strip()
        except OCRUnavailable:
            raise
        except Exception as error:
            raise OCRUnavailable(
                f"第{page_number}页OCR识别失败，请提供更清晰的文本版本。"
            ) from error


def configured_ocr_provider():
    mode = os.getenv("OCR_MODE", "disabled")
    if mode == "disabled":
        return UnavailableOCRProvider()
    if mode != "tesseract":
        raise OCRUnavailable("OCR模式配置无效，请管理员核查。")
    try:
        return TesseractOCRProvider(
            os.getenv("OCR_DATA_PATH", "data/tessdata"),
            os.getenv("OCR_LANGUAGES", "chi_sim+eng"),
            int(os.getenv("OCR_DPI", "180")),
            int(os.getenv("OCR_MAX_PIXELS", "8000000")),
            int(os.getenv("OCR_MAX_PAGES", "10")),
        )
    except ValueError as error:
        raise OCRUnavailable("OCR配置无效，请管理员核查。") from error


def ocr_ready():
    try:
        if os.getenv("OCR_MODE", "disabled") != "tesseract":
            return False
        provider = configured_ocr_provider()
        return all(
            importlib.util.find_spec(name) is not None
            for name in ("tesserocr", "pypdfium2")
        ) and all(
            (provider.data_path / (name + ".traineddata")).is_file()
            for name in provider.languages.split("+")
        )
    except (OCRUnavailable, ValueError):
        return False
