#!/usr/bin/env python3
from __future__ import annotations

import json
from contextlib import nullcontext

from common import REPO_ROOT, bool_env, http_request, is_cluster_internal_url, load_env, port_forward, resolve_elasticsearch_env


def main() -> None:
    env = resolve_elasticsearch_env(load_env())
    base = env["ELASTICSEARCH_URL"].rstrip("/")
    user = env["ELASTICSEARCH_USERNAME"]
    password = env["ELASTICSEARCH_PASSWORD"]
    search_namespace = env.get("SEARCH_NAMESPACE", "observability")
    search_cluster_name = env.get("SEARCH_CLUSTER_NAME", "search-stack")
    use_port_forward = bool_env(env.get("ELASTICSEARCH_PORT_FORWARD"), default=is_cluster_internal_url(base))
    runtime = REPO_ROOT / "runtime/elasticsearch"

    context = (
        port_forward(search_namespace, f"svc/{search_cluster_name}-es-http", 9200, 9200)
        if use_port_forward
        else nullcontext()
    )

    with context:
        if use_port_forward:
            base = "https://127.0.0.1:9200"

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
