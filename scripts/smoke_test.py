#!/usr/bin/env python3
from __future__ import annotations

from contextlib import nullcontext

from common import bool_env, http_request, is_cluster_internal_url, load_env, port_forward, resolve_elasticsearch_env, run


def main() -> None:
    env = resolve_elasticsearch_env(load_env())
    observability_namespace = env.get("SEARCH_NAMESPACE", "observability")
    investigations_namespace = env.get("INVESTIGATION_NAMESPACE", "investigations")
    checks = [
        ["kubectl", "rollout", "status", "deployment/edge-ingest-api", "-n", observability_namespace, "--timeout=300s"],
        ["kubectl", "rollout", "status", "deployment/edge-ingest-worker", "-n", observability_namespace, "--timeout=300s"],
        ["kubectl", "rollout", "status", "deployment/investigation-ops-api", "-n", investigations_namespace, "--timeout=300s"],
        ["kubectl", "rollout", "status", "deployment/investigation-ops-worker", "-n", investigations_namespace, "--timeout=300s"],
    ]
    for cmd in checks:
        run(cmd)
        print("ok", " ".join(cmd[2:4]))

    es_url = env["ELASTICSEARCH_URL"].rstrip("/")
    use_es_port_forward = bool_env(env.get("ELASTICSEARCH_PORT_FORWARD"), default=is_cluster_internal_url(es_url))
    es_context = (
        port_forward(observability_namespace, f"svc/{env.get('SEARCH_CLUSTER_NAME', 'search-stack')}-es-http", 9200, 9200)
        if use_es_port_forward
        else nullcontext()
    )
    with es_context:
        if use_es_port_forward:
            es_url = "https://127.0.0.1:9200"
        es = http_request("GET", es_url + "/_cluster/health", username=env["ELASTICSEARCH_USERNAME"], password=env["ELASTICSEARCH_PASSWORD"], insecure=True)
        print("elasticsearch_status", es["status"])

    with port_forward(observability_namespace, "svc/edge-ingest", 18080, 80):
        edge_health = http_request("GET", "http://127.0.0.1:18080/health")
        print("edge_ingest_health", edge_health)

    with port_forward(investigations_namespace, "svc/investigation-ops-api", 18081, 8080):
        investigation_health = http_request("GET", "http://127.0.0.1:18081/healthz")
        print("investigation_api_health", investigation_health)


if __name__ == "__main__":
    main()
