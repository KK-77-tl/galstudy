"""Run a loopback-only WebGAL/Next experiment against a synthetic account.

Requires prepare_webgal.py, the project virtualenv, frontend/node_modules and Edge.
The API fixture deliberately shares its synthetic session with the browser.
"""

from datetime import datetime, timezone
import hashlib
import http.server
import json
import mimetypes
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import unquote
import urllib.request
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "data/webgal-poc/engine"
ARTIFACTS = ROOT / "docs"
ASSETS = ROOT / "frontend/public/assets"
ASSET_NAMES = {"classroom.webp", "library.webp", "shiori.png", "haruka.png", "rin.png", "shiori-happy.png", "haruka-gentle.png"}
sys.path.insert(0, str(ROOT))
from backend.characters import CHARACTERS


def scene(current):
    node = current["node"]
    background = "library" if node["scene"] == "library" else "classroom"
    profile = next(
        (profile for profile in CHARACTERS.values() if profile["name"] == node["speaker"]),
        CHARACTERS["shiori"],
    )
    portrait = profile.get("expressions", {}).get(node["expression"], profile["portrait"])
    figure = Path(portrait).name
    text = node["text"].replace("\n", " ").replace(";", "，")
    lines = [
        f"changeBg:{background}.webp -next;",
        f"changeFigure:{figure} -next;",
        f'{node["speaker"]}（{node["expression"]}）:{text};',
    ]
    choices = [
        f'{choice["label"]}:step-{current["node_id"]}-{choice["id"]}.txt'
        for choice in node["choices"]
    ]
    lines.append("choose:" + "|".join(choices) + ";" if choices else "end;")
    return "\n".join(lines).encode("utf-8")


def handler_for(api, course_id, graph, observation):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, body, content, status=200):
            self.send_response(status)
            self.send_header("Content-Type", content)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def forward(self, response):
            self.respond(response.content, response.headers["content-type"], response.status_code)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            if length > 4096:
                self.send_error(413)
                return
            body = self.rfile.read(length)
            if self.path.startswith("/api/"):
                response = api.post(self.path, content=body, headers={"Content-Type": self.headers.get("Content-Type", "application/json")})
                self.forward(response)
                return
            if self.path != "/advance":
                self.send_error(404)
                return
            request = json.loads(body)
            previous = api.get(f"/api/courses/{course_id}/play").json()
            if observation["reject_next"]:
                request["version"] -= 1
                observation["reject_next"] = False
            response = api.post(f"/api/courses/{course_id}/play", json=request)
            observation["statuses"].append(response.status_code)
            if response.status_code == 200:
                current = response.json()
                observation["events"].append({
                    "choice": request["choice"],
                    "question": previous["node"]["question"],
                    "node": current["node_id"],
                    "score": current["score"],
                    "version": current["version"],
                    "feedback_present": bool(current["feedback"]),
                })
            self.forward(response)

        def do_GET(self):
            path = unquote(self.path.split("?", 1)[0])
            if path.startswith("/api/"):
                self.forward(api.get(self.path))
                return
            if path == "/current":
                self.forward(api.get(f"/api/courses/{course_id}/play"))
                return
            if path.endswith("/game/config.txt"):
                body = ("Game_name:GalStudy original PoC;\nGame_key:galstudy-poc;\n"
                        "Title_img:classroom.webp;\nEnable_Continue:false;\n"
                        "Enable_Appreciation:false;\nEnable_flowchart:false;").encode()
                content = "text/plain; charset=utf-8"
            elif path.endswith("/game/scene/start.txt"):
                current = api.get(f"/api/courses/{course_id}/play").json()
                body = scene(current)
                content = "text/plain; charset=utf-8"
            elif "/game/scene/step-" in path:
                parent, choice_id = Path(path).stem.removeprefix("step-").split("-", 1)
                source = graph.nodes[parent]
                target = next(choice.target for choice in source.choices if choice.id == choice_id)
                observation["reads"].append({"parent": parent, "choice": choice_id})
                body = scene({"node_id": target, "node": graph.nodes[target].model_dump()})
                content = "text/plain; charset=utf-8"
            elif "/game/background/" in path or "/game/figure/" in path or path.startswith("/assets/"):
                name = Path(path).name
                if name not in ASSET_NAMES:
                    self.send_error(404)
                    return
                body = (ASSETS / name).read_bytes()
                content = mimetypes.guess_type(name)[0]
            elif path.endswith(".scss") or path.endswith("/game/userStyleSheet.css"):
                body, content = b"", "text/css"
            elif path.endswith("/game/animation/animationTable.json"):
                body, content = b"[]", "application/json"
            elif path.endswith("/game/template/template.json"):
                body = b'{"name":"GalStudy research","webgal-version":"4.6.7"}'
                content = "application/json"
            else:
                relative = path.removeprefix("/engine/").strip("/") or "index.html"
                target = (ENGINE / relative).resolve()
                if relative == "webgal-serviceworker.js" or not target.is_relative_to(ENGINE.resolve()) or not target.is_file():
                    self.send_error(404)
                    return
                body = target.read_bytes()
                content = mimetypes.guess_type(relative)[0] or "application/octet-stream"
            self.respond(body, content)

    return Handler


def prepare_host(directory, upstream, log):
    host = directory / "host"
    (host / "app/custom").mkdir(parents=True)
    for name in ["page.jsx", "layout.jsx"]:
        shutil.copyfile(ROOT / "scripts/fixtures/webgal-host" / name, host / "app" / name)
    source = json.dumps((ROOT / "frontend/app/study/page.tsx").as_posix())
    styles = json.dumps((ROOT / "frontend/app/globals.css").as_posix())
    (host / "app/custom/page.jsx").write_text(f"import Study from {source};\nimport {styles};\nexport default Study;\n", encoding="utf-8")
    shutil.copyfile(ROOT / "frontend/postcss.config.mjs", host / "postcss.config.mjs")
    modules = ROOT / "frontend/node_modules"
    versions = {name: json.loads((modules / name / "package.json").read_text())["version"] for name in ["next", "react", "react-dom"]}
    (host / "package.json").write_text(json.dumps({"private": True, "dependencies": versions}))
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(host / "node_modules"), str(modules)], check=True, stdout=log, stderr=log)
    else:
        (host / "node_modules").symlink_to(modules, target_is_directory=True)
    config = {"turbopack": {"root": str(ROOT)}}
    routes = [{"source": source, "destination": upstream + source} for source in ["/engine/:path*", "/api/:path*", "/assets/:path*", "/current", "/advance"]]
    (host / "next.config.js").write_text("module.exports=" + json.dumps(config) + ";module.exports.rewrites=async()=>" + json.dumps(routes))
    return host, modules / "next/dist/bin/next", versions


def browser_check(base, api, course_id, observation, report):
    from playwright.sync_api import sync_playwright, expect, TimeoutError as PlaywrightTimeout

    def current():
        return api.get(f"/api/courses/{course_id}/play").json()

    def restart():
        response = api.post(f"/api/courses/{course_id}/play/restart", json={"version": current()["version"]})
        response.raise_for_status()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=os.getenv("E2E_BROWSER", "msedge"), headless=True)
        report["browser"] = browser.version
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        http_errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("response", lambda response: http_errors.append({"url": response.url.removeprefix(base), "status": response.status}) if response.status >= 400 else None)
        page.goto(base)
        cdp = page.context.new_cdp_session(page)
        cdp.send("Performance.enable")

        def metrics(label):
            cdp.send("HeapProfiler.collectGarbage")
            values = {item["name"]: item["value"] for item in cdp.send("Performance.getMetrics")["metrics"]}
            report["heap_samples"].append({
                "label": label,
                "js_heap_used_bytes": int(values["JSHeapUsedSize"]),
                "documents": values["Documents"],
                "frames": values["Frames"],
                "cumulative_task_seconds": values["TaskDuration"],
                "cumulative_script_seconds": values["ScriptDuration"],
            })

        def resources(target):
            return target.evaluate("""() => performance.getEntriesByType('resource').map(item => ({
                path: new URL(item.name).pathname, decoded_body_bytes: item.decodedBodySize,
                encoded_body_bytes: item.encodedBodySize, transfer_bytes: item.transferSize,
                duration_ms: item.duration
            }))""")

        frame = page.frame_locator("#engine")

        def mount():
            page.locator("#mount").click()
            frame.get_by_text("PRESS THE SCREEN TO START", exact=True).click(timeout=15000)
            try:
                frame.get_by_text("简体中文", exact=True).click(timeout=1500)
            except PlaywrightTimeout:
                pass
            frame.get_by_text("开始游戏", exact=True).first.locator("..").locator("..").click(timeout=10000)
            page.wait_for_timeout(1000)

        def unmount(label):
            page.locator("#unmount").click()
            expect(page.locator("iframe")).to_have_count(0)
            page.wait_for_timeout(300)
            metrics(label)

        def reveal():
            for _ in range(2):
                frame.locator("#textBoxMain").click(force=True)
                page.wait_for_timeout(700)

        def choose(choice_id, status=200):
            before = current()
            choice = next(item for item in before["node"]["choices"] if item["id"] == choice_id)
            item = frame.locator("#chooseContainer").get_by_text(choice["label"], exact=True)
            with page.expect_response(lambda response: response.url.endswith("/advance")) as response_info:
                item.click(timeout=10000)
            assert response_info.value.status == status
            expect(page.locator("#bridge-state")).to_have_text("idle")
            if status == 200:
                expect(page.locator("#bridge-error")).to_have_text("")
                assert observation["events"][-1]["choice"] == choice_id
            else:
                expect(page.locator("#bridge-error")).to_contain_text(str(status))
                assert current() == before
                expect(item).to_be_visible()
            page.wait_for_timeout(700)

        metrics("host_before_mount")
        mount()
        reveal()
        assert current()["node_id"] == "start" and current()["version"] == 0
        assert {item["choice"] for item in observation["reads"] if item["parent"] == "start"} == {"concept", "practice"}
        report["prefetch_preserved_start"] = True
        observation["reject_next"] = True
        choose("concept", status=409)
        report["rejected_click_preserved_stage_and_save"] = True
        choose("concept")
        assert current()["node_id"] == "concept"
        reveal()
        choose("next")
        assert current()["node_id"] == "quiz"
        reveal()
        metrics("webgal_quiz")
        report["webgal_resources"] = resources(frame.locator("body"))
        report["webgal_host_resources"] = resources(page)
        page.screenshot(path=str(ARTIFACTS / "webgal-quiz.png"), full_page=True)
        saved = current()
        unmount("after_unmount_1")
        mount()
        reveal()
        assert current() == saved
        expect(frame.locator("#chooseContainer").get_by_text("合上书，凭记忆复述要点", exact=True)).to_be_visible()
        report["resume_node"] = saved["node_id"]
        report["resume_version"] = saved["version"]
        choose("recall")
        assert current()["node_id"] == "success" and current()["score"] == 1
        assert observation["events"][-1]["feedback_present"]
        assert any(item["path"].endswith("shiori-happy.png") for item in resources(frame.locator("body")))
        page.screenshot(path=str(ARTIFACTS / "webgal-success.png"), full_page=True)
        restart()
        unmount("after_unmount_2")
        mount()
        reveal()
        choose("practice")
        assert current()["node_id"] == "practice"
        reveal()
        choose("next")
        reveal()
        choose("reread")
        assert current()["node_id"] == "review" and current()["score"] == 0
        assert observation["events"][-1]["feedback_present"]
        assert len(api.get("/api/wrong-answers").json()) == 1
        assert any(item["path"].endswith("haruka-gentle.png") for item in resources(frame.locator("body")))
        page.screenshot(path=str(ARTIFACTS / "webgal-review.png"), full_page=True)
        unmount("after_unmount_3")
        assert errors == [], errors
        report["page_errors"] = errors
        report["http_errors"] = http_errors
        page.close()

        restart()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        custom_errors = []
        page.on("pageerror", lambda error: custom_errors.append(str(error)))
        page.goto(base + "/custom")
        page.get_by_role("button", name="我的课程", exact=True).click()
        page.get_by_role("button", name="进入项目", exact=False).click()
        page.get_by_role("button", name="继续剧情", exact=False).click()
        page.get_by_role("button", name="和小栞一起理解概念", exact=True).click()
        page.get_by_role("button", name="我明白了，去图书馆试试", exact=True).click()
        expect(page.locator(".player-heading")).to_be_visible()
        page.locator(".player-bg").evaluate("image => image.decode()")
        page.locator(".player-sprite").evaluate("image => image.decode()")
        cdp = page.context.new_cdp_session(page)
        cdp.send("Performance.enable")
        metrics("custom_quiz")
        report["custom_resources"] = resources(page)
        page.screenshot(path=str(ARTIFACTS / "engine-custom-quiz.png"), full_page=True)
        with page.expect_response(
            lambda response: response.url.endswith(f"/api/courses/{course_id}/play")
            and response.request.method == "POST"
        ) as graded:
            page.get_by_role("button", name="合上书，凭记忆复述要点", exact=True).click()
        assert graded.value.status == 200
        assert current()["node_id"] == "success" and current()["score"] == 1
        expect(page.locator(".player-sprite")).to_have_attribute("src", "/assets/shiori-happy.png")
        page.locator(".player-sprite").evaluate("image => image.decode()")
        page.screenshot(path=str(ARTIFACTS / "engine-custom-success.png"), full_page=True)
        assert custom_errors == [], custom_errors
        report["custom_page_errors"] = custom_errors
        browser.close()


def main():
    if not (ENGINE / "index.html").is_file():
        raise RuntimeError("Run scripts/prepare_webgal.py first")
    directory = ROOT / "test-results" / ("webgal-" + uuid4().hex)
    directory.mkdir(parents=True)
    os.environ.update({
        "DATABASE_URL": "sqlite:///" + (directory / "probe.db").as_posix(),
        "LLM_MODE": "demo", "LLM_CHAT_MODE": "demo", "IMAGE_GENERATOR": "mock",
    })
    from backend.main import app
    from backend.story import DEMO
    from fastapi.testclient import TestClient

    report = {
        "status": "running",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "engine": "WebGAL 4.6.7",
        "host": "Next.js production build, React client component, same-origin iframe",
        "heap_samples": [],
        "heap_scope": "CDP JSHeapUsedSize after explicit GC, excludes native and GPU memory",
        "cpu_scope": "Counters since Performance.enable, distinct interaction paths, unsuitable for cross-route CPU comparison",
        "resource_scope": "Resource Timing decoded bodies, includes repeated requests, excludes navigation HTML",
        "viewport": {"width": 1440, "height": 1000},
        "real_model_calls": 0,
        "real_payments": 0,
        "scratch_directory": str(directory),
        "limitations": [
            "DOM-class choice bridge is specific to WebGAL 4.6.7",
            "Server save restores a graph node, excludes native engine saves and mid-line state",
            "Two generated expression variants, additional expressions use their default sprite",
            "Public fixed Demo scripts may be prefetched, private course story streaming is untested",
            "Optional Live2D scripts absent from upstream archive return 404",
            "Three unmount samples do not establish absence of leaks",
        ],
    }
    report_path = ARTIFACTS / "webgal-same-origin-result.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    observation = {
        "events": [], "reads": [], "statuses": [], "reject_next": False,
    }
    next_process = None
    with TestClient(app) as api, (directory / "next.log").open("w", encoding="utf-8") as log:
        response = api.post("/api/auth/register", json={"email": uuid4().hex + "@example.com", "password": "WebGAL-original-probe-2026"})
        response.raise_for_status()
        course = api.post("/api/courses", json={"title": "原创引擎对照实验", "demo": True})
        course.raise_for_status()
        course_id = course.json()["id"]
        api.get(f"/api/courses/{course_id}/play").raise_for_status()
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_for(api, course_id, DEMO, observation))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, cli, versions = prepare_host(directory, f"http://127.0.0.1:{server.server_port}", log)
            report["versions"] = versions
            env = {**os.environ, "NEXT_TELEMETRY_DISABLED": "1"}
            subprocess.run(["node", str(cli), "build", str(host), "--webpack"], env=env, stdout=log, stderr=log, check=True, timeout=240)
            with socket.socket() as listening:
                listening.bind(("127.0.0.1", 0))
                port = listening.getsockname()[1]
            next_process = subprocess.Popen(["node", str(cli), "start", str(host), "--hostname", "127.0.0.1", "--port", str(port)], env=env, stdout=log, stderr=log)
            base = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 30
            while True:
                if next_process.poll() is not None:
                    raise RuntimeError("Next host exited, see " + str(directory / "next.log"))
                try:
                    with urllib.request.urlopen(base, timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    if time.monotonic() > deadline:
                        raise RuntimeError("Next host readiness timeout")
                    time.sleep(0.1)
            browser_check(base, api, course_id, observation, report)
            report.update(observation)
            report["engine_archive_bytes"] = (ROOT / "data/webgal-poc/release.zip").stat().st_size
            report["engine_archive_sha256"] = hashlib.sha256((ROOT / "data/webgal-poc/release.zip").read_bytes()).hexdigest()
            report["engine_files"] = [
                {
                    "path": file.relative_to(ENGINE).as_posix(),
                    "bytes": file.stat().st_size,
                    "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                }
                for file in sorted(ENGINE.rglob("*")) if file.is_file()
            ]
            report["status"] = "passed"
        except BaseException as error:
            report.update(observation)
            report["status"] = "failed"
            report["error"] = repr(error)
            raise
        finally:
            if next_process is not None and next_process.poll() is None:
                next_process.terminate()
                next_process.wait(timeout=15)
            report["next_stopped"] = next_process is not None and next_process.poll() is not None
            server.shutdown()
            server.server_close()
            thread.join()
            report["fixture_stopped"] = not thread.is_alive()
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    report["api_context_closed"] = True
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "events": report["events"],
        "heap_samples": report["heap_samples"],
        "next_stopped": report["next_stopped"],
        "fixture_stopped": report["fixture_stopped"],
        "api_context_closed": report["api_context_closed"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
