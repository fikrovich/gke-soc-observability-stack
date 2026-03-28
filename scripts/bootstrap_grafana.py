#!/usr/bin/env python3
from __future__ import annotations

import json
from contextlib import nullcontext
from pathlib import Path

from common import REPO_ROOT, bool_env, http_request, is_cluster_internal_url, load_env, port_forward, render_text, resolve_elasticsearch_env


def upsert_datasource(base: str, user: str, password: str, payload: dict) -> None:
    uid = payload["uid"]
    try:
        existing = http_request("GET", f"{base}/api/datasources/uid/{uid}", username=user, password=password)
        payload["id"] = existing["id"]
        http_request("PUT", f"{base}/api/datasources/uid/{uid}", username=user, password=password, json_body=payload)
    except Exception:
        http_request("POST", f"{base}/api/datasources", username=user, password=password, json_body=payload)


def folder_title(folder_uid: str) -> str:
    return " ".join(part.capitalize() for part in folder_uid.split("-"))


def _http_status(exc: Exception, status_code: int) -> bool:
    return f"HTTP {status_code} " in str(exc)


def ensure_folder(base: str, user: str, password: str, folder_uid: str) -> None:
    if not folder_uid:
        return
    payload = {"uid": folder_uid, "title": folder_title(folder_uid)}
    try:
        http_request("GET", f"{base}/api/folders/{folder_uid}", username=user, password=password)
        return
    except RuntimeError as exc:
        if not _http_status(exc, 404):
            raise

    try:
        http_request("POST", f"{base}/api/folders", username=user, password=password, json_body=payload)
    except RuntimeError as exc:
        if _http_status(exc, 412):
            http_request("GET", f"{base}/api/folders/{folder_uid}", username=user, password=password)
            return
        raise


def main() -> None:
    env = resolve_elasticsearch_env(load_env())
    base = env["GRAFANA_URL"].rstrip("/")
    user = env.get("GRAFANA_USERNAME", env.get("GRAFANA_ADMIN_USER", "admin"))
    password = env.get("GRAFANA_PASSWORD", env.get("GRAFANA_ADMIN_PASSWORD", ""))
    grafana_namespace = env.get("GRAFANA_NAMESPACE", "grafana")
    use_port_forward = bool_env(env.get("GRAFANA_PORT_FORWARD"), default=is_cluster_internal_url(base))
    runtime = REPO_ROOT / "runtime/grafana"

    context = port_forward(grafana_namespace, "svc/grafana", 3000, 80) if use_port_forward else nullcontext()
    with context:
        if use_port_forward:
            base = "http://127.0.0.1:3000"

        datasources = json.loads(render_text((runtime / "datasources.template.json").read_text(), env))
        for ds in datasources:
            upsert_datasource(base, user, password, ds)
            print(f"upserted datasource {ds['uid']}")

        dashboards_dir = runtime / "dashboards"
        dashboard_payloads: list[dict] = []
        folder_uids: set[str] = set()
        for path in sorted(dashboards_dir.glob("*.json")):
            payload = json.loads(path.read_text())
            dashboard_payloads.append(payload)
            folder_uid = payload.get("meta", {}).get("folderUid", "")
            if folder_uid:
                folder_uids.add(folder_uid)

        alert_rules = json.loads((runtime / "alert-rules.json").read_text())
        for rule in alert_rules:
            folder_uid = rule.get("folderUID", "")
            if folder_uid:
                folder_uids.add(folder_uid)

        for folder_uid in sorted(folder_uids):
            ensure_folder(base, user, password, folder_uid)
            print(f"ensured folder {folder_uid}")

        contact_points = json.loads(render_text((runtime / "contact-points.template.json").read_text(), env))
        for cp in contact_points:
            uid = cp.get("uid", "")
            if uid:
                try:
                    http_request("PUT", f"{base}/api/v1/provisioning/contact-points/{uid}", username=user, password=password, json_body=cp)
                except RuntimeError:
                    http_request("POST", f"{base}/api/v1/provisioning/contact-points", username=user, password=password, json_body=cp)
            else:
                http_request("POST", f"{base}/api/v1/provisioning/contact-points", username=user, password=password, json_body=cp)
        print("applied contact points")

        policies = json.loads((runtime / "policies.json").read_text())
        http_request("PUT", f"{base}/api/v1/provisioning/policies", username=user, password=password, json_body=policies)
        print("applied notification policy")

        for rule in alert_rules:
            try:
                http_request("PUT", f"{base}/api/v1/provisioning/alert-rules/{rule['uid']}", username=user, password=password, json_body=rule)
            except Exception:
                http_request("POST", f"{base}/api/v1/provisioning/alert-rules", username=user, password=password, json_body=rule)
        print("applied alert rules")

        for path, payload in zip(sorted(dashboards_dir.glob("*.json")), dashboard_payloads, strict=False):
            dashboard = {
                "dashboard": payload["dashboard"],
                "folderUid": payload.get("meta", {}).get("folderUid"),
                "overwrite": True,
            }
            http_request("POST", f"{base}/api/dashboards/db", username=user, password=password, json_body=dashboard)
            print(f"imported dashboard {path.stem}")


if __name__ == "__main__":
    main()
