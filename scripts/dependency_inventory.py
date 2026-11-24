"""Record installed Python packages and locked frontend license metadata."""

import importlib.metadata as metadata
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
python = []
for distribution in metadata.distributions():
    info = distribution.metadata
    licenses = [
        str(path)
        for path in distribution.files or []
        if Path(str(path)).name.upper().startswith(("LICENSE", "COPYING", "NOTICE"))
    ]
    declared = (
        info.get("License-Expression")
        or info.get("License")
        or "; ".join(
            value
            for value in info.get_all("Classifier", [])
            if value.startswith("License ::")
        )
    )
    python.append(
        {
            "name": info["Name"],
            "version": distribution.version,
            "license_metadata": declared,
            "license_files": licenses,
        }
    )
lock = json.loads((ROOT / "frontend/package-lock.json").read_text())
frontend = [
    {
        "path": path,
        "version": package.get("version"),
        "dev": package.get("dev", False),
        "optional": package.get("optional", False),
        "license_metadata": package.get("license"),
        "installed": (ROOT / "frontend" / path).is_dir(),
    }
    for path, package in lock["packages"].items()
    if path
]
report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "python_environment": "isolated .venv, includes runtime and dev dependencies",
    "python": sorted(python, key=lambda package: package["name"].lower()),
    "frontend_lock": frontend,
    "scope": "Package-declared license metadata and Python notice locations. Native bundled components, generated artwork rights and release-image notice inclusion require separate verification.",
}
(ROOT / "docs/dependency-inventory.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(
    f"Recorded {len(python)} Python packages and {len(frontend)} frontend lock entries"
)
