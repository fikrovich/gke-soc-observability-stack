# Getting Started

This doc is for engineers who want to run the stack, not just read about it.

## Before You Start
Required tooling:
- `gcloud`
- `kubectl`
- `terraform`
- `helm`
- `docker`
- Python 3

Assumption:
- you are targeting GKE and want the production-shaped deployment path in this repo

## Step 1: Read The Model First
Before provisioning anything, read:
- `docs/architecture.md`
- `docs/workflows.md`
- `docs/lessons.md`

If you skip that, the runtime bootstrap will look arbitrary. It is not arbitrary.

## Step 2: Configure Environment
1. Copy `.env.example` to `.env`
2. Fill in project, region, image tags, and secret values

## Step 3: Provision The Base Platform
```bash
make tf-init
make tf-plan
make tf-apply
```

Then fetch credentials:
```bash
make gke-credentials
```

## Step 4: Install Platform Services
```bash
make install-platform
```

This installs the base layer only:
- ECK
- Kafka
- Grafana
- Elasticsearch and Kibana resources

## Step 5: Apply Apps And Secrets
```bash
make render-secrets
make apply-apps
```

This applies:
- monitoring manifests
- observability manifests
- investigations manifests
- rendered Kubernetes secrets

## Step 6: Bootstrap Runtime Objects
```bash
make bootstrap-runtime
```

This creates or updates:
- Kafka topics and configs
- Elasticsearch ILM policies, templates, aliases, and pipelines
- Grafana datasources, dashboards, contact points, policies, and generic alert rules
- the copied search CA secret used by investigation workers

## Step 7: Validate
```bash
make smoke
```

Expected outcome:
- ingest endpoints respond
- Kafka topics exist
- Elasticsearch runtime objects are present
- Grafana assets import cleanly
- investigation service endpoints resolve

## Optional Producer Validation
The repo uses Cloudflare Logpush as the reference producer example.

If you use Cloudflare, validate:
- the HTTP endpoint returns success only after Kafka durability
- the batch size and auth model match your Logpush configuration
- dashboards measure freshness through queue lag and indexed event timestamps

If you use another producer, keep the same durability and observability expectations.

## If You Are Adapting The Stack
If you do not need the exact same shape, the safest things to preserve are:
- split ingest API and worker roles
- Kafka topics and DLQ pattern
- Elasticsearch runtime objects under version control
- investigation playbooks separated from transport logic

The safest things to tune for your own environment are:
- replica counts
- node sizes
- retention windows
- exposure model for the public endpoint and dashboards
