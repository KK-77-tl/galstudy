"""Prefetch the local CPU layout and table weights for the pinned Docling experiment."""

import hashlib
import json
import os
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
DESTINATION = ROOT / "data/docling-models"
os.environ.setdefault("HF_HOME", str(ROOT / "data/docling-hf-cache"))
system_proxies = urllib.request.getproxies()
for protocol in ["http", "https"]:
    proxy = system_proxies.get(protocol)
    if proxy:
        os.environ.setdefault(protocol.upper() + "_PROXY", proxy)

from docling.datamodel.pipeline_options import LayoutObjectDetectionOptions
from huggingface_hub import HfApi, snapshot_download


def main():
    DESTINATION.mkdir(exist_ok=True, parents=True)
    layout = LayoutObjectDetectionOptions().model_spec
    requests = [
        {"repo": layout.repo_id, "revision": "8f39ad3c0b4c58e9c2d2c84a38465abf757272d8", "patterns": None},
        {"repo": "docling-project/docling-models", "revision": "fc0f2d45e2218ea24bce5045f58a389aed16dc23",
         "patterns": ["model_artifacts/tableformer/**", "LICENSE*", "README*"]},
    ]
    records = []
    api = HfApi()
    for request in requests:
        info = api.model_info(request["repo"], revision=request["revision"], files_metadata=True)
        print(json.dumps({"repo": request["repo"], "commit": info.sha}, ensure_ascii=False), flush=True)
        directory = DESTINATION / request["repo"].replace("/", "--")
        snapshot_download(
            repo_id=request["repo"], revision=info.sha, local_dir=directory,
            allow_patterns=request["patterns"],
        )
        files = []
        for file in sorted(directory.rglob("*")):
            if not file.is_file() or ".cache" in file.parts:
                continue
            digest = hashlib.sha256()
            with file.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            files.append({"path": file.relative_to(directory).as_posix(), "bytes": file.stat().st_size, "sha256": digest.hexdigest()})
        records.append({
            "repo": request["repo"], "requested_revision": request["revision"], "commit": info.sha,
            "source": "https://huggingface.co/" + request["repo"],
            "license": info.card_data.get("license") if info.card_data else None,
            "files": files,
        })
    tessdata = ROOT / "data/tessdata"
    ocr_manifest = json.loads((tessdata / "sources.json").read_text(encoding="utf-8"))
    osd_url = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/" + ocr_manifest["revision"] + "/osd.traineddata"
    osd = tessdata / "osd.traineddata"
    if not osd.exists():
        with urllib.request.urlopen(osd_url, timeout=60) as response:
            osd.write_bytes(response.read())
    report = {
        "docling_slim": "2.150.1", "models": records,
        "tesseract_osd": {"source": osd_url, "bytes": osd.stat().st_size, "sha256": hashlib.sha256(osd.read_bytes()).hexdigest()},
    }
    (DESTINATION / "sources.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "prepared", "models": len(records), "bytes": sum(file["bytes"] for record in records for file in record["files"])}, indent=2))


if __name__ == "__main__":
    main()
