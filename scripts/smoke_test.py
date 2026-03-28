#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from common import REPO_ROOT, http_request, load_env, run


def main() -> None:
    env = load_env()
    checks = [
        ["kubectl", "rollout", "status", "deployment/edge-ingest-api", "-n", "observability", "--timeout=60s"],
        ["kubectl", "rollout", "status", "deployment/edge-ingest-worker", "-n", "observability", "--timeout=60s"],
        ["kubectl", "rollout", "status", "deployment/investigation-ops-api", "-n", "investigations", "--timeout=60s"],
        ["kubectl", "rollout", "status", "deployment/investigation-ops-worker", "-n", "investigations", "--timeout=60s"],
    ]
    for cmd in checks:
        run(cmd)
        print("ok", " ".join(cmd[2:4]))

    es = http_request("GET", env["ELASTICSEARCH_URL"].rstrip("/") + "/_cluster/health", username=env["ELASTICSEARCH_USERNAME"], password=env["ELASTICSEARCH_PASSWORD"], insecure=True)
    print("elasticsearch_status", es["status"])


if __name__ == "__main__":
    main()
