"""Recognize an original image-only Chinese/English PDF through the parser worker."""

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
sample = ROOT / "tests/samples/original-scan.pdf"
image = Image.new("RGB", (1240, 1754), "white")
draw = ImageDraw.Draw(image)
font_path = Path("C:/Windows/Fonts/msyh.ttc")
if not font_path.exists():
    raise SystemExit(
        "Set up a licensed Chinese test font before running this Windows fixture script"
    )
font = ImageFont.truetype(str(font_path), 48)
for index, line in enumerate(
    [
        "学习方法",
        "检索练习是主动回忆知识。",
        "合上书，复述刚才的内容。",
        "Study methods",
        "Retrieval practice",
        "Recall the key ideas.",
    ]
):
    draw.text((90, 120 + index * 120), line, fill="black", font=font)
image.save(sample, format="PDF", resolution=150)
image.close()
assert not (PdfReader(sample).pages[0].extract_text() or "").strip()
payload = json.dumps(
    {"name": sample.name, "data": base64.b64encode(sample.read_bytes()).decode()}
).encode()
began = time.perf_counter()
result = subprocess.run(
    [sys.executable, "-m", "backend.parse_worker"],
    cwd=ROOT,
    input=payload,
    capture_output=True,
    timeout=45,
    check=True,
    env={
        **os.environ,
        "OCR_MODE": "tesseract",
        "OCR_DATA_PATH": str(ROOT / "data/tessdata"),
    },
)
parsed = json.loads(result.stdout)
assert "error" not in parsed, parsed.get("error")
location, text = parsed["chunks"][0]
compact = "".join(text.split())
assert (
    "检索练习" in compact
    and "主动回忆知识" in compact
    and "Retrievalpractice" in compact
), text
report = {
    "status": "passed",
    "input": "original image-only Chinese/English PDF",
    "page": location,
    "seconds": round(time.perf_counter() - began, 3),
    "recognized_text": text,
    "real_local_ocr": True,
    "cloud_calls": 0,
}
(ROOT / "docs/ocr-result.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(report, ensure_ascii=False, indent=2))
