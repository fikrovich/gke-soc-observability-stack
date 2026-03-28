SHELL := /bin/zsh
.ONESHELL:
.DEFAULT_GOAL := help

REPO := $(realpath $(dir $(lastword $(MAKEFILE_LIST))))
ENV_FILE ?= $(REPO)/.env
TF_DIR := $(REPO)/infra/gcp

ifneq (,$(wildcard $(ENV_FILE)))
include $(ENV_FILE)
export
endif

help:
	@echo "Targets:"
	@echo "  tf-init                  Terraform init"
	@echo "  tf-plan                  Terraform plan"
	@echo "  tf-apply                 Terraform apply"
	@echo "  install-platform         Install ECK, Kafka, Grafana, Elasticsearch, Kibana"
	@echo "  render-secrets           Render secret templates from .env"
	@echo "  apply-apps               Apply monitoring, ingest, and investigation manifests"
	@echo "  bootstrap-kafka          Create or update Kafka topics"
	@echo "  bootstrap-elasticsearch  Apply Elasticsearch runtime objects"
	@echo "  bootstrap-grafana        Apply Grafana runtime objects"
	@echo "  bootstrap-investigation-ca Copy Elastic CA into investigations"
	@echo "  bootstrap-runtime        Run all bootstrap steps"
	@echo "  smoke                    Validate core services and runtime objects"
	@echo "  build-images             Build local service images"
	@echo "  validate                 Static validation of templates and runtime assets"

tf-init:
	terraform -chdir=$(TF_DIR) init

tf-plan:
	terraform -chdir=$(TF_DIR) plan

tf-apply:
	terraform -chdir=$(TF_DIR) apply

install-platform:
	$(REPO)/scripts/install_platform.sh

render-secrets:
	python3 $(REPO)/scripts/render_secret_templates.py

apply-apps: render-secrets
	kubectl apply -f $(REPO)/rendered/secrets
	kubectl apply -f $(REPO)/rendered/k8s/namespaces/monitoring
	kubectl apply -f $(REPO)/rendered/k8s/namespaces/observability
	kubectl apply -f $(REPO)/rendered/k8s/namespaces/investigations

bootstrap-kafka:
	python3 $(REPO)/scripts/bootstrap_kafka.py

bootstrap-elasticsearch:
	python3 $(REPO)/scripts/bootstrap_elasticsearch.py

bootstrap-grafana:
	python3 $(REPO)/scripts/bootstrap_grafana.py

bootstrap-investigation-ca:
	$(REPO)/scripts/bootstrap_investigation_ca.sh

bootstrap-runtime: bootstrap-kafka bootstrap-elasticsearch bootstrap-grafana bootstrap-investigation-ca

smoke:
	python3 $(REPO)/scripts/smoke_test.py

build-images:
	docker build -t $(EDGE_INGEST_API_IMAGE) $(REPO)/services/edge-ingest
	docker build -t $(INVESTIGATION_OPS_IMAGE) $(REPO)/services/investigation-ops

validate:
	python3 $(REPO)/scripts/validate.py
