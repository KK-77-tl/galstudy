import hashlib
import json
from pathlib import Path
import urllib.request
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent
root = ROOT / "data/postgresql-17.12"
root.mkdir(parents=True, exist_ok=True)
archive = root / "binaries.zip"
url = "https://get.enterprisedb.com/postgresql/postgresql-17.12-1-windows-x64-binaries.zip"
if not archive.exists():
    partial = root / "binaries.zip.partial"
    with urllib.request.urlopen(url, timeout=60) as response, partial.open(
        "wb"
    ) as output:
        total = int(response.headers["Content-Length"])
        size = 0
        last = 0
        while block := response.read(1024 * 1024):
            output.write(block)
            size += len(block)
            if size - last >= 50 * 1024 * 1024:
                print(
                    f"Downloaded {size // 1024**2} / {total // 1024**2} MiB", flush=True
                )
                last = size
    if size != total:
        raise RuntimeError("Incomplete archive")
    partial.rename(archive)
with archive.open("rb") as source:
    digest = hashlib.file_digest(source, "sha256").hexdigest()
if digest != "a2cd8a774389347b70be7748ac4a37ef43cb6ee539c5fc3e85ae264b15e4a04c":
    raise RuntimeError(
        "PostgreSQL archive differs from the verified development download"
    )
with ZipFile(archive) as bundle:
    for item in bundle.infolist():
        if item.filename.startswith(("pgsql/bin/", "pgsql/lib/", "pgsql/share/")):
            target = (root / item.filename).resolve()
            if not target.is_relative_to(root.resolve()):
                raise RuntimeError("Unsafe archive member")
            bundle.extract(item, root)
report = {"source": url, "bytes": archive.stat().st_size, "sha256": digest}
(root / "source.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2), flush=True)
