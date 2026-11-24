import json, urllib.request, pathlib

repos = [
    "OpenWebGAL/WebGAL",
    "docling-project/docling",
    "Mintplex-Labs/anything-llm",
    "SillyTavern/SillyTavern",
    "Comfy-Org/ComfyUI",
    "inkle/ink",
    "y-lohse/inkjs",
    "open-spaced-repetition/ts-fsrs",
]
out = []
for repo in repos:
    try:

        def get(path):
            req = urllib.request.Request(
                "https://api.github.com/repos/" + repo + path,
                headers={"User-Agent": "GalStudy-research"},
            )
            return json.load(urllib.request.urlopen(req, timeout=25))

        meta = get("")
        release = get("/releases/latest")
        out.append(
            dict(
                repo=repo,
                stars=meta["stargazers_count"],
                branch=meta["default_branch"],
                license=meta["license"]["spdx_id"] if meta.get("license") else None,
                version=release.get("tag_name"),
                url=meta["html_url"],
            )
        )
    except Exception as e:
        out.append(dict(repo=repo, error=str(e)))
pathlib.Path("docs/research-metadata.json").write_text(
    json.dumps(out, indent=2), encoding="utf-8"
)
print(json.dumps(out, indent=2))
