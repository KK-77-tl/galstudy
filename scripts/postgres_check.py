"""Run the acceptance suite in an isolated, project-local PostgreSQL cluster."""

import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from uuid import uuid4
import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "data/postgresql-17.12/pgsql/bin"
if not (BIN / "initdb.exe").exists():
    raise SystemExit(
        "Place official PostgreSQL 17.12 Windows binaries in data/postgresql-17.12/pgsql first. See docs/postgresql-verification.md."
    )
directory = ROOT / "test-results" / ("postgres-" + uuid4().hex)
directory.mkdir(parents=True)
cluster = directory / "cluster"
password_file = directory / "password"
password = secrets.token_hex(24)
password_file.write_text(password, encoding="ascii")
database = "galstudy_test_" + uuid4().hex
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def command(*args, timeout=60):
    # Detached PostgreSQL children inherit standard handles on Windows. A file
    # avoids keeping a captured pipe open after pg_ctl has already exited.
    with (directory / "control.log").open("ab") as output:
        return subprocess.run(
            [str(BIN / args[0]), *map(str, args[1:])],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=True,
            creationflags=flags,
        )


command(
    "initdb.exe",
    "-D",
    cluster,
    "-U",
    "galstudy_test",
    "-A",
    "scram-sha-256",
    "--pwfile",
    password_file,
    "--locale=C",
    "--encoding=UTF8",
)
started = False
try:
    command(
        "pg_ctl.exe",
        "-D",
        cluster,
        "-l",
        directory / "postgres.log",
        "-o",
        f"-h 127.0.0.1 -p {port} -c shared_buffers=32MB -c max_connections=40",
        "-w",
        "start",
    )
    started = True
    connect = {
        "host": "127.0.0.1",
        "port": port,
        "user": "galstudy_test",
        "password": password,
    }
    with psycopg.connect(**connect, dbname="postgres", autocommit=True) as connection:
        version = connection.execute("SELECT version()").fetchone()[0]
        connection.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database))
        )
    env = {
        **os.environ,
        "GALSTUDY_TEST_DATABASE_URL": f"postgresql+psycopg://galstudy_test:{password}@127.0.0.1:{port}/{database}",
        "PYTHONIOENCODING": "utf-8",
    }
    began = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=flags,
        timeout=240,
    )
    output = result.stdout.decode("utf-8", errors="replace").replace("\r\n", "\n")
    (ROOT / "docs/postgresql-test-result.txt").write_text(output, encoding="utf-8")
    with psycopg.connect(**connect, dbname=database) as connection:
        counts_before = {
            table: connection.execute(
                sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
            ).fetchone()[0]
            for table in ["users", "courses", "saves", "chat_messages", "orders", "payment_events", "entitlements", "refunds"]
        }
        fingerprint_query = sql.SQL(
            "SELECT md5(COALESCE(string_agg(md5(row_to_json(t)::text), '' ORDER BY id), '')) FROM {} t"
        )
        fingerprints_before = {
            table: connection.execute(
                fingerprint_query.format(sql.Identifier(table))
            ).fetchone()[0]
            for table in counts_before
        }
    subprocess.run(
        [sys.executable, "-m", "backend.db"],
        cwd=ROOT,
        env={**env, "DATABASE_URL": env["GALSTUDY_TEST_DATABASE_URL"]},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=True,
        timeout=30,
        creationflags=flags,
    )
    with psycopg.connect(**connect, dbname=database) as connection:
        counts_after = {
            table: connection.execute(
                sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
            ).fetchone()[0]
            for table in counts_before
        }
        assert (
            counts_before == counts_after
        ), "Repeated migration changed existing row counts"
        fingerprints_after = {
            table: connection.execute(
                fingerprint_query.format(sql.Identifier(table))
            ).fetchone()[0]
            for table in counts_before
        }
        assert (
            fingerprints_before == fingerprints_after
        ), "Repeated migration changed existing data"
        versions = [
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]
        tables = connection.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
        ).fetchone()[0]
    report = {
        "version": version,
        "migrations": versions,
        "public_tables": tables,
        "test_exit_code": result.returncode,
        "test_seconds": round(time.monotonic() - began, 2),
        "repeat_migration_preserves_rows": counts_before == counts_after,
        "repeat_migration_preserves_content": fingerprints_before == fingerprints_after,
        "validated_row_counts": counts_after,
        "database_isolation": "new galstudy_test_* database in a new test-results cluster",
        "listen_addresses": "127.0.0.1",
        "authentication": "scram-sha-256",
        "server_stopped": False,
    }
    print("\n".join(output.splitlines()[-12:]), flush=True)
finally:
    if started:
        command("pg_ctl.exe", "-D", cluster, "-m", "fast", "-w", "stop")
        if "report" in globals():
            report["server_stopped"] = True
    password_file.unlink(missing_ok=True)
    if "report" in globals():
        (ROOT / "docs/postgresql-result.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, indent=2), flush=True)
if result.returncode:
    raise SystemExit(result.returncode)
