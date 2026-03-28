#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from common import REPO_ROOT, load_env, http_request, render_text


def upsert_datasource(base: str, user: str, password: str, payload: dict) -> None:
    uid = payload["uid"]
    try:
        existing = http_request("GET", f"{base}/api/datasources/uid/{uid}", username=user, password=password)
        payload["id"] = existing["id"]
        http_request("PUT", f"{base}/api/datasources/uid/{uid}", username=user, password=password, json_body=payload)
    except Exception:
        http_request("POST", f"{base}/api/datasources", username=user, password=password, json_body=payload)


def main() -> None:
    env = load_env()
    base = env["GRAFANA_URL"].rstrip("/")
    user = env["GRAFANA_USERNAME"]
    password = env["GRAFANA_PASSWORD"]
    runtime = REPO_ROOT / "runtime/grafana"

    datasources = json.loads(render_text((runtime / "datasources.template.json").read_text(), env))
    for ds in datasources:
        upsert_datasource(base, user, password, ds)
        print(f"upserted datasource {ds['uid']}")

    contact_points = json.loads(render_text((runtime / "contact-points.template.json").read_text(), env))
    for cp in contact_points:
        uid = cp.get("uid", "")
        if uid:
            http_request("PUT", f"{base}/api/v1/provisioning/contact-points/{uid}", username=user, password=password, json_body=cp)
        else:
            http_request("POST", f"{base}/api/v1/provisioning/contact-points", username=user, password=password, json_body=cp)
    print("applied contact points")

    policies = json.loads((runtime / "policies.json").read_text())
    http_request("PUT", f"{base}/api/v1/provisioning/policies", username=user, password=password, json_body=policies)
    print("applied notification policy")

    alert_rules = json.loads((runtime / "alert-rules.json").read_text())
    for rule in alert_rules:
        try:
            http_request("PUT", f"{base}/api/v1/provisioning/alert-rules/{rule['uid']}", username=user, password=password, json_body=rule)
        except Exception:
            http_request("POST", f"{base}/api/v1/provisioning/alert-rules", username=user, password=password, json_body=rule)
    print("applied alert rules")

    dashboards_dir = runtime / "dashboards"
    for path in sorted(dashboards_dir.glob("*.json")):
        payload = json.loads(path.read_text())
        dashboard = {
            "dashboard": payload["dashboard"],
            "folderUid": payload.get("meta", {}).get("folderUid"),
            "overwrite": True,
        }
        http_request("POST", f"{base}/api/dashboards/db", username=user, password=password, json_body=dashboard)
        print(f"imported dashboard {path.stem}")


if __name__ == "__main__":
    main()
