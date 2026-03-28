#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from common import REPO_ROOT


def main() -> None:
    required = [
        REPO_ROOT / "k8s/platform/elasticsearch/search-stack.yaml",
        REPO_ROOT / "k8s/platform/elasticsearch/kibana.yaml",
        REPO_ROOT / "k8s/platform/kafka/values.yaml",
        REPO_ROOT / "k8s/platform/grafana/values.yaml",
        REPO_ROOT / "runtime/kafka/topics.json",
        REPO_ROOT / "runtime/elasticsearch/ilm-edge-logs-policy.json",
        REPO_ROOT / "runtime/grafana/datasources.template.json",
    ]
    for path in required:
        if not path.exists():
            raise SystemExit(f"missing required file: {path}")
    json.loads((REPO_ROOT / "runtime/kafka/topics.json").read_text())
    json.loads((REPO_ROOT / "runtime/elasticsearch/ilm-edge-logs-policy.json").read_text())
    json.loads((REPO_ROOT / "runtime/grafana/datasources.template.json").read_text())
    print("validation passed")


if __name__ == "__main__":
    main()
