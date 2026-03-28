#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from common import REPO_ROOT, load_env, render_text

TEMPLATE_FILES = [
    REPO_ROOT / "k8s/namespaces/observability/edge-ingest-secret.template.yaml",
    REPO_ROOT / "k8s/namespaces/monitoring/es-exporter-creds.template.yaml",
    REPO_ROOT / "k8s/namespaces/investigations/investigation-ops-secret.template.yaml",
]


def main() -> None:
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

    for template in TEMPLATE_FILES:
        rendered = render_text(template.read_text(), env)
        target_name = template.name.replace(".template", "")
        (out_dir / target_name).write_text(rendered)

    for source in (REPO_ROOT / "k8s/namespaces").rglob("*.yaml"):
        if source.name.endswith(".template.yaml"):
            continue
        relative = source.relative_to(REPO_ROOT / "k8s")
        target = rendered_k8s_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        rendered = render_text(source.read_text(), env)
        target.write_text(rendered)

    print(out_dir)


if __name__ == "__main__":
    main()
