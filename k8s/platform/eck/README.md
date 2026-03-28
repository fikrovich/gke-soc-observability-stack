Install the ECK operator pinned to the live cluster major/minor version:

```bash
kubectl apply -f https://download.elastic.co/downloads/eck/3.2.0/crds.yaml
kubectl apply -f https://download.elastic.co/downloads/eck/3.2.0/operator.yaml
```

The rest of the Elasticsearch and Kibana configuration is in:
- `k8s/platform/elasticsearch/search-stack.yaml`
- `k8s/platform/elasticsearch/kibana.yaml`
