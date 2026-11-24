"""Inspect official upstream files, without installing or copying product code."""

import json
import hashlib
import urllib.request
from pathlib import Path


def fetch(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "GalStudy-technical-research"}
    )
    return urllib.request.urlopen(req, timeout=30).read()


metadata = json.loads(Path("docs/research-metadata.json").read_text())
results = []
for item in metadata:
    base = f'https://raw.githubusercontent.com/{item["repo"]}/{item["branch"]}/'
    record = {"repo": item["repo"], "checks": []}
    for file in [
        "README.md",
        "LICENSE",
        "LICENSE.md",
        "LICENSE.txt",
        "package.json",
        "pyproject.toml",
    ]:
        try:
            body = fetch(base + file).decode("utf-8")
            record["checks"].append(
                {
                    "file": file,
                    "url": base + file,
                    "bytes": len(body),
                    "sha256": hashlib.sha256(body.encode()).hexdigest(),
                }
            )
        except Exception:
            continue
    results.append(record)
paths = [
    "packages/webgal/src/Core/WebGAL.ts",
    "packages/webgal/src/Core/controller/storage/saveGame.ts",
]
for path in paths:
    body = fetch("https://raw.githubusercontent.com/OpenWebGAL/WebGAL/main/" + path)
    results.append(
        {
            "repo": "OpenWebGAL/WebGAL",
            "source": path,
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
        }
    )
Path("docs/upstream-source-checks.json").write_text(
    json.dumps({"projects": results, "webgal_paths": paths}, indent=2), encoding="utf-8"
)
print(json.dumps({"projects": len(results), "webgal_paths": paths[:70]}, indent=2))
