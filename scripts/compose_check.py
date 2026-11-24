"""Run the real Compose stack in an isolated WSL Docker project.

Requires Docker Engine, Compose and Buildx in an existing Ubuntu WSL distro.
Generated credentials and named volumes belong only to this synthetic test.
"""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parent.parent


def linux_path(path):
    path = path.resolve()
    return "/mnt/" + path.drive[0].lower() + path.as_posix()[2:]


def main():
    run_id = uuid4().hex[:12]
    project = "galstudycheck" + run_id
    directory = ROOT / "test-results" / ("compose-" + run_id)
    directory.mkdir(parents=True)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    base = f"http://localhost:{port}"
    environment = directory / "compose.env"
    environment.write_text(
        "POSTGRES_PASSWORD=" + secrets.token_hex(24) + "\n"
        + "PAYMENT_MOCK_SECRET=" + secrets.token_hex(32) + "\n"
        + "WORKSHOP_REVIEW_TOKEN=" + secrets.token_hex(32) + "\n"
        + f"APP_ORIGIN={base}\nCOOKIE_SECURE=false\n"
        + "LLM_MODE=demo\nLLM_CHAT_MODE=demo\nIMAGE_GENERATOR=mock\nPAYMENT_PROVIDER=mock\n",
        encoding="utf-8",
    )
    override = directory / "override.yaml"
    override.write_text(
        "services:\n  api:\n    env_file: !override ["
        + json.dumps(linux_path(environment)) + "]\n"
        + "  web:\n    ports: !override ["
        + json.dumps(f"127.0.0.1:{port}:3000") + "]\n",
        encoding="utf-8",
    )
    build_proxy = os.getenv("COMPOSE_BUILD_PROXY")
    if build_proxy:
        proxy_arguments = json.dumps({"HTTP_PROXY": build_proxy, "HTTPS_PROXY": build_proxy})
        override.write_text(
            "services:\n  api:\n    env_file: !override ["
            + json.dumps(linux_path(environment)) + "]\n"
            + "    build:\n      args: " + proxy_arguments + "\n"
            + "  web:\n    ports: !override ["
            + json.dumps(f"127.0.0.1:{port}:3000") + "]\n"
            + "    build:\n      args: " + proxy_arguments + "\n",
            encoding="utf-8",
        )
    # Explicitly selected, digest-verified registry paths can avoid a failing
    # Docker Hub route while preserving the exact upstream base content.
    base_override = directory / "bases.yaml"
    base_lines = ["services:"]
    for service, argument, variable in [("api", "PYTHON_BASE", "COMPOSE_PYTHON_BASE"), ("web", "NODE_BASE", "COMPOSE_NODE_BASE")]:
        if os.getenv(variable):
            base_lines.extend([f"  {service}:", "    build:", "      args:", f"        {argument}: " + json.dumps(os.environ[variable])])
    if len(base_lines) > 1:
        base_override.write_text("\n".join(base_lines) + "\n", encoding="utf-8")
    docker_command = ["docker"]
    if build_proxy:
        docker_command = [
            "env", "HTTP_PROXY=" + build_proxy, "HTTPS_PROXY=" + build_proxy,
            "NO_PROXY=localhost,127.0.0.1,::1,api,db,web", "docker",
        ]
    prefix = [
        "wsl.exe", "-d", os.getenv("COMPOSE_WSL_DISTRO", "Ubuntu"), "--user", "root",
        "--cd", linux_path(ROOT), "--", *docker_command, "compose", "--project-name", project,
        "--env-file", linux_path(environment), "-f", "compose.yaml", "-f", linux_path(override),
    ]
    if base_override.exists():
        prefix.extend(["-f", linux_path(base_override)])
    report_path = ROOT / "docs/compose-result.json"
    report = {
        "status": "running", "created_at": datetime.now(timezone.utc).isoformat(),
        "project": project, "scratch_directory": str(directory), "base_url": base,
        "real_model_calls": 0, "real_payments": 0,
        "base_references": {key: os.getenv(key) for key in ["COMPOSE_NODE_BASE", "COMPOSE_PYTHON_BASE"] if os.getenv(key)},
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    with (directory / "compose.log").open("wb") as log:
        wsl = [
            "wsl.exe", "-d", os.getenv("COMPOSE_WSL_DISTRO", "Ubuntu"),
            "--user", "root", "--",
        ]
        # An open stdin keeps WSL alive while Windows runs browser assertions.
        keepalive = subprocess.Popen(
            wsl + ["cat"], stdin=subprocess.PIPE, stdout=log, stderr=log,
        )
        proxy_config = "/run/systemd/system/docker.service.d/" + project + ".conf"

        def compose(*args, timeout=600, capture=False):
            result = subprocess.run(
                prefix + list(args), stdout=subprocess.PIPE if capture else log,
                stderr=log, timeout=timeout, check=True,
            )
            return result.stdout.decode("utf-8", errors="replace") if capture else None

        try:
            if build_proxy:
                active = subprocess.check_output(wsl + ["docker", "ps", "-q"], stderr=log)
                if active.strip():
                    raise RuntimeError("Proxy setup requires an idle Docker daemon")
                setup = (
                    'mkdir -p /run/systemd/system/docker.service.d && '
                    'printf "[Service]\\nEnvironment=HTTP_PROXY=%s\\nEnvironment=HTTPS_PROXY=%s\\n'
                    'Environment=NO_PROXY=localhost,127.0.0.1,::1,api,db,web\\n" '
                    '"$1" "$1" > "$2" && systemctl daemon-reload && systemctl restart docker'
                )
                subprocess.run(
                    wsl + ["sh", "-s", "--", build_proxy, proxy_config], input=setup.encode(),
                    stdout=log, stderr=log, check=True, timeout=30,
                )
            compose("config", "--quiet")
            for attempt in range(3):
                try:
                    compose("up", "--build", "--detach", "--wait", "--wait-timeout", "180", timeout=1200)
                    report["build_attempts"] = attempt + 1
                    break
                except subprocess.CalledProcessError:
                    log.flush()
                    tail = (directory / "compose.log").read_bytes()[-20000:].decode("utf-8", errors="replace")
                    transient = any(message in tail for message in [
                        "TLS handshake timeout", "i/o timeout", "connection reset by peer",
                    ])
                    transient = transient or ("failed to do request" in tail and "EOF" in tail)
                    if not transient or attempt == 2:
                        raise
                    time.sleep(1)
            report["healthy_services"] = [
                json.loads(line)["Service"]
                for line in compose("ps", "--format", "json", capture=True).splitlines()
            ]
            with httpx.Client(base_url=base, trust_env=False, timeout=30) as client:
                health = client.get("/api/health")
                health.raise_for_status()
                assert health.json()["database"] == "postgresql"
                report["health"] = health.json()
                response = client.post("/api/auth/register", json={
                    "email": run_id + "@example.com", "password": secrets.token_urlsafe(24),
                })
                response.raise_for_status()
                response = client.post("/api/courses", json={"title": "Compose persistence probe", "demo": True})
                response.raise_for_status()
                course_id = response.json()["id"]
                current = client.get(f"/api/courses/{course_id}/play").json()
                response = client.post(f"/api/courses/{course_id}/play", json={"choice": "concept", "version": current["version"]})
                response.raise_for_status()
                saved = response.json()
                assert saved["node_id"] == "concept"
                source = ROOT / "tests/samples/original.docx"
                response = client.post(f"/api/courses/{course_id}/files", files={"file": (source.name, source.read_bytes())})
                response.raise_for_status()
                deadline = time.monotonic() + 45
                while True:
                    detail = client.get(f"/api/courses/{course_id}").json()
                    file = detail["files"][0]
                    if file["status"] == "ready":
                        break
                    assert file["status"] != "failed", file
                    if time.monotonic() > deadline:
                        raise RuntimeError("Container parser timed out")
                    time.sleep(0.3)
                download_path = f'/api/courses/{course_id}/files/{file["id"]}'
                original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
                assert hashlib.sha256(client.get(download_path).content).hexdigest() == original_hash
                report["private_upload_download_sha256"] = original_hash
                compose("stop")
                compose("up", "--detach", "--no-build", "--wait", "--wait-timeout", "120")
                resumed = client.get(f"/api/courses/{course_id}/play")
                resumed.raise_for_status()
                assert resumed.json()["node_id"] == saved["node_id"]
                assert resumed.json()["version"] == saved["version"]
                assert hashlib.sha256(client.get(download_path).content).hexdigest() == original_hash
                report["restart_preserves_session_save_and_file"] = True
            browser = subprocess.run(
                [sys.executable, str(ROOT / "scripts/e2e.py")], cwd=ROOT,
                env={**os.environ, "E2E_BASE_URL": base}, stdout=log, stderr=log,
                timeout=300,
            )
            report["browser_exit_code"] = browser.returncode
            assert browser.returncode == 0, "Browser regression failed, see compose.log"
            dump = "/tmp/galstudy-compose-check.dump"
            compose("exec", "-T", "db", "pg_dump", "-U", "galstudy", "-d", "galstudy", "-Fc", "-f", dump)
            restore_database = "restore_" + run_id
            compose("exec", "-T", "db", "createdb", "-U", "galstudy", restore_database)
            compose("exec", "-T", "db", "pg_restore", "-U", "galstudy", "-d", restore_database, "--exit-on-error", dump)
            query = "SELECT (SELECT count(*) FROM users),(SELECT count(*) FROM courses),(SELECT count(*) FROM saves),(SELECT count(*) FROM source_files);"
            counts = []
            for database in ["galstudy", restore_database]:
                counts.append(compose("exec", "-T", "db", "psql", "-U", "galstudy", "-d", database, "-At", "-c", query, capture=True).strip())
            assert counts[0] == counts[1]
            report["backup_restore_row_counts"] = counts[0]
            report["backup_restore_counts_match"] = True
            restored_hash = compose(
                "exec", "-T", "db", "psql", "-U", "galstudy", "-d", restore_database,
                "-At", "-c", f"SELECT encode(sha256(data),'hex') FROM source_files WHERE id='{file['id']}';",
                capture=True,
            ).strip()
            assert restored_hash == original_hash
            restored_save = compose(
                "exec", "-T", "db", "psql", "-U", "galstudy", "-d", restore_database,
                "-At", "-c", f"SELECT node,version FROM saves WHERE course_id='{course_id}';",
                capture=True,
            ).strip()
            assert restored_save == f"{saved['node_id']}|{saved['version']}"
            report["backup_restore_file_and_save_match"] = True
            report["status"] = "passed"
        except BaseException as error:
            report["status"] = "failed"
            report["error"] = repr(error)
            raise
        finally:
            try:
                compose("down", timeout=60)
                report["containers_stopped"] = True
            finally:
                if build_proxy:
                    subprocess.run(
                        wsl + ["sh", "-s", "--", proxy_config],
                        input=b'rm -f "$1"; systemctl daemon-reload',
                        stdout=log, stderr=log, timeout=15, check=False,
                    )
                keepalive.stdin.close()
                keepalive.wait(timeout=15)
                report["wsl_keepalive_stopped"] = keepalive.poll() is not None
                report["test_volumes_retained"] = True
                report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
