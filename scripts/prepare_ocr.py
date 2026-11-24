"""Download two official Tesseract language models to ignored project storage."""

import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
directory = ROOT / "data/tessdata"
directory.mkdir(parents=True, exist_ok=True)
manifest = directory / "sources.json"
if manifest.exists():
    revision = json.loads(manifest.read_text())["revision"]
else:
    request = urllib.request.Request(
        "https://api.github.com/repos/tesseract-ocr/tessdata_fast/commits/main",
        headers={"User-Agent": "GalStudy-local-OCR-setup"},
    )
    revision = json.load(urllib.request.urlopen(request, timeout=30))["sha"]
records = []
for name in ["eng.traineddata", "chi_sim.traineddata", "LICENSE"]:
    url = f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{revision}/{name}"
    path = directory / name
    if not path.exists():
        with urllib.request.urlopen(url, timeout=30) as response:
            body = response.read(20 * 1024 * 1024 + 1)
        if len(body) > 20 * 1024 * 1024:
            raise RuntimeError("OCR model exceeds setup download limit")
        path.write_bytes(body)
    records.append(
        {
            "file": name,
            "source": url,
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    )
report = {"revision": revision, "models": records}
manifest.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
