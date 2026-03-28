# Operational Lessons

This repo is valuable because it encodes production-grade lessons, not just component assembly.

## 1. Acknowledge After Durability, Not After Search
If the producer receives success before the event is durably queued, your pipeline can lie about availability. The ingest API in this stack treats Kafka as the acknowledgement boundary.

## 2. Realtime Depends On Queue Health, Not Only Search Health
Elasticsearch can be green while users still see delayed logs. Freshness depends on Kafka lag, worker throughput, and write-path concurrency.

## 3. Shard Layout Is A Throughput Decision
Primary shard count is not only a storage question. It changes how many write lanes the hot tier can use.

## 4. Retention And Capacity Must Be Managed Together
Hot/warm tiering helps, but it does not remove the need to size retention against actual ingest volume and shard movement.

## 5. Runtime Objects Are Part Of The Product
Kafka topics, Elasticsearch ILM/templates/aliases, and Grafana alerting objects change behavior just as much as application code does.

## 6. Investigation Logic Should Be Data-Driven
Playbooks belong in structured configuration, not hard-coded decision trees. That keeps the webhook intake generic and the investigation logic reviewable.

## 7. Public Value Comes From Concrete Tradeoffs
A useful platform repo should show:
- what was optimized
- what bottlenecks exist
- which tradeoffs were chosen
- how operators should validate the design under pressure
