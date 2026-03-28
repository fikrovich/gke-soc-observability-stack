#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from common import REPO_ROOT, load_env, http_request, render_text


def main() -> None:
    env = load_env()
    base = env["ELASTICSEARCH_URL"].rstrip("/")
    user = env["ELASTICSEARCH_USERNAME"]
    password = env["ELASTICSEARCH_PASSWORD"]
    runtime = REPO_ROOT / "runtime/elasticsearch"

    for name in ["edge-logs-policy", "investigation-results-policy"]:
        payload = json.loads((runtime / f"ilm-{name}.json").read_text())
        http_request("PUT", f"{base}/_ilm/policy/{name}", username=user, password=password, json_body=payload, insecure=True)
        print(f"applied ILM {name}")

    for name in ["edge-logs-template", "investigation-results-template"]:
        payload = json.loads((runtime / f"index-template-{name}.json").read_text())
        http_request("PUT", f"{base}/_index_template/{name}", username=user, password=password, json_body=payload, insecure=True)
        print(f"applied index template {name}")

    pipeline = json.loads((runtime / "ingest-pipeline-EdgeEvents.json").read_text())
    http_request("PUT", f"{base}/_ingest/pipeline/EdgeEvents", username=user, password=password, json_body=pipeline, insecure=True)
    print("applied ingest pipeline EdgeEvents")

    aliases = json.loads((runtime / "bootstrap-aliases.json").read_text())
    for item in aliases:
        index_name = item["index"]
        try:
            http_request("GET", f"{base}/{index_name}", username=user, password=password, insecure=True)
        except Exception:
            http_request("PUT", f"{base}/{index_name}", username=user, password=password, json_body=item["body"], insecure=True)
            print(f"created bootstrap index {index_name}")


if __name__ == "__main__":
    main()
