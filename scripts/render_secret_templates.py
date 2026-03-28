#!/usr/bin/env python3
from __future__ import annotations

import argparse
from urllib.parse import urlsplit, urlunsplit

from common import REPO_ROOT, kubectl_secret_value, load_env, render_text

TEMPLATE_FILES = [
    REPO_ROOT / "k8s/namespaces/observability/edge-ingest-secret.template.yaml",
    REPO_ROOT / "k8s/namespaces/monitoring/es-exporter-creds.template.yaml",
    REPO_ROOT / "k8s/namespaces/investigations/investigation-ops-secret.template.yaml",
]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--scope", choices=["all", "grafana"], default="all")
    return p


def _elastic_password(env: dict[str, str]) -> str:
    if env.get("ELASTICSEARCH_PASSWORD"):
        return env["ELASTICSEARCH_PASSWORD"]
    namespace = env.get("SEARCH_NAMESPACE", "observability")
    cluster_name = env.get("SEARCH_CLUSTER_NAME", "search-stack")
    return kubectl_secret_value(namespace, f"{cluster_name}-es-elastic-user", "elastic")


def _inject_basic_auth(url: str, username: str, password: str) -> str:
    parsed = urlsplit(url)
    netloc = parsed.hostname or ""
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    if username or password:
        netloc = f"{username}:{password}@{netloc}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def resolve_runtime_env(env: dict[str, str]) -> dict[str, str]:
    resolved = dict(env)
    resolved.setdefault("ELASTICSEARCH_USERNAME", "elastic")
    resolved.setdefault("INVESTIGATION_ELASTICSEARCH_USERNAME", resolved["ELASTICSEARCH_USERNAME"])
    elastic_password = _elastic_password(resolved)
    resolved.setdefault("ELASTICSEARCH_PASSWORD", elastic_password)
    resolved.setdefault("EDGE_INGEST_ES_PASSWORD", elastic_password)
    resolved.setdefault("INVESTIGATION_ELASTICSEARCH_PASSWORD", elastic_password)
    if not resolved.get("ES_EXPORTER_URI"):
        resolved["ES_EXPORTER_URI"] = _inject_basic_auth(
            resolved["ELASTICSEARCH_URL"],
            resolved["ELASTICSEARCH_USERNAME"],
            resolved["ELASTICSEARCH_PASSWORD"],
        )
    return resolved


def main() -> None:
    args = parser().parse_args()
    env = load_env()
    out_dir = REPO_ROOT / "rendered/secrets"
    out_dir.mkdir(parents=True, exist_ok=True)
    rendered_k8s_root = REPO_ROOT / "rendered/k8s"
    rendered_k8s_root.mkdir(parents=True, exist_ok=True)

    grafana_secret = render_text(
        """apiVersion: v1
kind: Secret
metadata:
  name: grafana
  namespace: grafana
type: Opaque
stringData:
  admin-user: ${GRAFANA_ADMIN_USER}
  admin-password: ${GRAFANA_ADMIN_PASSWORD}
""",
        env,
    )
    (out_dir / "grafana-admin-secret.yaml").write_text(grafana_secret)

    k8s_env = env
    if args.scope == "grafana":
        pass
    else:
        resolved_env = resolve_runtime_env(env)
        k8s_env = resolved_env
        for template in TEMPLATE_FILES:
            rendered = render_text(template.read_text(), resolved_env)
            target_name = template.name.replace(".template", "")
            (out_dir / target_name).write_text(rendered)

    for source in (REPO_ROOT / "k8s").rglob("*.yaml"):
        if source.name.endswith(".template.yaml"):
            continue
        relative = source.relative_to(REPO_ROOT / "k8s")
        target = rendered_k8s_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        rendered = render_text(source.read_text(), k8s_env)
        target.write_text(rendered)

    print(out_dir)


if __name__ == "__main__":
    main()
