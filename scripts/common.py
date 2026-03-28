from __future__ import annotations

import base64
import json
import os
import re
import shlex
import socket
import subprocess
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"
PLACEHOLDER_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


def load_env(path: Path | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env_file_override = env.get("ENV_FILE")
    path = path or (Path(env_file_override).expanduser() if env_file_override else ENV_FILE)
    if path.exists():
        for raw_line in path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env.setdefault(key.strip(), value.strip())
    return env


def render_text(text: str, env: dict[str, str]) -> str:
    missing: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in env:
            missing.add(key)
            return match.group(0)
        return env[key]

    rendered = PLACEHOLDER_PATTERN.sub(replace, text)
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(sorted(missing))}")
    return rendered


def bool_env(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def is_cluster_internal_url(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host.endswith(".svc") or host.endswith(".svc.cluster.local") or ".svc." in host


def run(cmd: Iterable[str], *, check: bool = True, capture_output: bool = True, text: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(cmd), check=check, capture_output=capture_output, text=text)


def kubectl_json(args: list[str]) -> Any:
    completed = run(["kubectl", *args, "-o", "json"])
    return json.loads(completed.stdout)


def kubectl_secret_value(namespace: str, name: str, key: str) -> str:
    encoded = run([
        "kubectl", "get", "secret", "-n", namespace, name, "-o", f"jsonpath={{.data.{key}}}"
    ]).stdout.strip()
    return base64.b64decode(encoded).decode()


def resolve_elasticsearch_env(env: dict[str, str]) -> dict[str, str]:
    resolved = dict(env)
    resolved.setdefault("SEARCH_NAMESPACE", "observability")
    resolved.setdefault("SEARCH_CLUSTER_NAME", "search-stack")
    resolved.setdefault("ELASTICSEARCH_USERNAME", "elastic")
    if not resolved.get("ELASTICSEARCH_PASSWORD"):
        resolved["ELASTICSEARCH_PASSWORD"] = kubectl_secret_value(
            resolved["SEARCH_NAMESPACE"],
            f"{resolved['SEARCH_CLUSTER_NAME']}-es-elastic-user",
            "elastic",
        )
    return resolved


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def http_request(
    method: str,
    url: str,
    *,
    username: str | None = None,
    password: str | None = None,
    json_body: Any | None = None,
    headers: dict[str, str] | None = None,
    insecure: bool = False,
) -> Any:
    payload = None if json_body is None else json.dumps(json_body).encode()
    request_headers = {"Accept": "application/json"}
    if json_body is not None:
        request_headers["Content-Type"] = "application/json"
    if headers:
        request_headers.update(headers)
    if username is not None and password is not None:
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        request_headers["Authorization"] = f"Basic {token}"
    request = urllib.request.Request(url, data=payload, headers=request_headers, method=method.upper())
    context = None
    if insecure:
        import ssl
        context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, timeout=60, context=context) as response:
            raw = response.read().decode()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        raise RuntimeError(f"HTTP {exc.code} {exc.reason} for {method.upper()} {url}: {detail}") from exc
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


@contextmanager
def port_forward(namespace: str, resource: str, local_port: int, remote_port: int):
    proc = subprocess.Popen(
        [
            "kubectl",
            "port-forward",
            "-n",
            namespace,
            resource,
            f"{local_port}:{remote_port}",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            with socket.socket() as sock:
                if sock.connect_ex(("127.0.0.1", local_port)) == 0:
                    break
            if proc.poll() is not None:
                output = proc.stdout.read() if proc.stdout else ""
                raise RuntimeError(f"port-forward failed: {output}")
            time.sleep(0.5)
        else:
            raise RuntimeError(f"Timed out waiting for port-forward on {local_port}")
        yield
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def latest_bundle_dir(root: Path) -> Path:
    bundles = sorted([p for p in root.iterdir() if p.is_dir()])
    if not bundles:
        raise RuntimeError(f"No export bundles in {root}")
    return bundles[-1]
