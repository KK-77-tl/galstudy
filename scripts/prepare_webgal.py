"""Prepare the pinned upstream engine in ignored research storage."""

import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
VERSION = "4.6.7"
SIZE = 52842728
SHA256 = "7baf45d78e5c5924a08fcd1974e776452b71b5477d8a6449e4e967c845b95578"
URL = f"https://github.com/OpenWebGAL/WebGAL/releases/download/{VERSION}/WebGAL-{VERSION}-web.zip"


def main():
    directory = ROOT / "data/webgal-poc"
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / "release.zip"
    if not archive.exists():
        partial = directory / "release.zip.partial"
        for _ in range(3):
            offset = partial.stat().st_size if partial.exists() else 0
            request = urllib.request.Request(URL, headers={"Range": f"bytes={offset}-"})
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    append = offset > 0 and response.status == 206
                    with partial.open("ab" if append else "wb") as output:
                        while chunk := response.read(1024 * 1024):
                            output.write(chunk)
                            if output.tell() > SIZE:
                                raise RuntimeError("Upstream archive exceeds pinned size")
            except OSError:
                continue
            if partial.stat().st_size == SIZE:
                break
        if not partial.exists() or partial.stat().st_size != SIZE:
            raise RuntimeError("Incomplete download retained for retry")
        if hashlib.sha256(partial.read_bytes()).hexdigest() != SHA256:
            raise RuntimeError("Upstream archive digest mismatch")
        partial.replace(archive)
    if archive.stat().st_size != SIZE or hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise RuntimeError("Existing archive does not match the pinned release")
    engine = directory / "engine"
    engine.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            if member.filename.startswith("game/") or member.is_dir():
                continue
            target = (engine / member.filename).resolve()
            if not target.is_relative_to(engine.resolve()):
                raise RuntimeError("Archive entry escapes research directory")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(package.read(member))
    license_url = f"https://raw.githubusercontent.com/OpenWebGAL/WebGAL/{VERSION}/LICENSE"
    license_path = directory / "LICENSE-WebGAL"
    if not license_path.exists():
        with urllib.request.urlopen(license_url, timeout=30) as response:
            license_path.write_bytes(response.read(100000))
    report = {"version": VERSION, "source": URL, "bytes": SIZE, "sha256": SHA256, "license_source": license_url, "excluded_prefix": "game/"}
    (directory / "source.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
