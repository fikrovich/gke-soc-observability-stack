#!/usr/bin/env python3
from __future__ import annotations

import json

from common import REPO_ROOT, load_env, run


def main() -> None:
    env = load_env()
    topics = json.loads((REPO_ROOT / "runtime/kafka/topics.json").read_text())
    namespace = env.get("KAFKA_NAMESPACE", "kafka")
    bootstrap = env.get("KAFKA_BOOTSTRAP_SERVER", "kafka.kafka.svc.cluster.local:9092")
    broker_replicas = max(1, int(env.get("KAFKA_BROKER_REPLICAS", "1")))
    replication_factor_override = env.get("KAFKA_TOPIC_REPLICATION_FACTOR_OVERRIDE")
    base_exec = ["kubectl", "exec", "-n", namespace, "kafka-broker-0", "--", "sh", "-lc"]
    existing = set(run([*base_exec, f"/opt/bitnami/kafka/bin/kafka-topics.sh --bootstrap-server {bootstrap} --list"]).stdout.splitlines())
    for topic in topics:
        name = topic["name"]
        desired_replication_factor = int(topic["replication_factor"])
        replication_factor = min(desired_replication_factor, broker_replicas)
        if replication_factor_override:
            replication_factor = int(replication_factor_override)
        if name not in existing:
            run([
                *base_exec,
                "/opt/bitnami/kafka/bin/kafka-topics.sh "
                f"--bootstrap-server {bootstrap} --create --if-not-exists --topic {name} "
                f"--partitions {topic['partitions']} --replication-factor {replication_factor}"
            ])
        config_entries = ",".join(f"{k}={v}" for k, v in topic.get("configs", {}).items())
        if config_entries:
            run([
                *base_exec,
                "/opt/bitnami/kafka/bin/kafka-configs.sh "
                f"--bootstrap-server {bootstrap} --entity-type topics --entity-name {name} --alter --add-config {config_entries}"
            ])
        print(f"bootstrapped topic {name} with replication_factor={replication_factor}")


if __name__ == "__main__":
    main()
