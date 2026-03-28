SHELL := /bin/zsh
.ONESHELL:
.DEFAULT_GOAL := help

REPO := $(realpath $(dir $(lastword $(MAKEFILE_LIST))))
ENV_FILE ?= $(REPO)/.env
TF_DIR := $(REPO)/infra/gcp
TF_ARGS ?=
export ENV_FILE

ifneq (,$(wildcard $(ENV_FILE)))
include $(ENV_FILE)
export
endif

export TF_VAR_project_id := $(PROJECT_ID)
export TF_VAR_access_token := $(shell gcloud auth print-access-token 2>/dev/null)
export TF_VAR_region := $(REGION)
export TF_VAR_cluster_name := $(CLUSTER_NAME)
export TF_VAR_cluster_deletion_protection := $(if $(CLUSTER_DELETION_PROTECTION),$(CLUSTER_DELETION_PROTECTION),false)
export TF_VAR_network_name := $(NETWORK_NAME)
export TF_VAR_subnet_name := $(SUBNET_NAME)
export TF_VAR_subnet_cidr := $(SUBNET_CIDR)
export TF_VAR_master_ipv4_cidr := $(MASTER_IPV4_CIDR)
export TF_VAR_authorized_networks := $(AUTHORIZED_NETWORKS_JSON)
export TF_VAR_router_name := $(ROUTER_NAME)
export TF_VAR_nat_name := $(NAT_NAME)
export TF_VAR_master_node_count := $(MASTER_NODE_COUNT)
export TF_VAR_master_machine_type := $(MASTER_MACHINE_TYPE)
export TF_VAR_master_disk_size_gb := $(MASTER_DISK_SIZE_GB)
export TF_VAR_master_disk_type := $(MASTER_DISK_TYPE)
export TF_VAR_hot_min_node_count := $(HOT_MIN_NODE_COUNT)
export TF_VAR_hot_max_node_count := $(HOT_MAX_NODE_COUNT)
export TF_VAR_hot_machine_type := $(HOT_MACHINE_TYPE)
export TF_VAR_hot_disk_size_gb := $(HOT_DISK_SIZE_GB)
export TF_VAR_hot_disk_type := $(HOT_DISK_TYPE)
export TF_VAR_warm_min_node_count := $(WARM_MIN_NODE_COUNT)
export TF_VAR_warm_max_node_count := $(WARM_MAX_NODE_COUNT)
export TF_VAR_warm_machine_type := $(WARM_MACHINE_TYPE)
export TF_VAR_warm_disk_size_gb := $(WARM_DISK_SIZE_GB)
export TF_VAR_warm_disk_type := $(WARM_DISK_TYPE)
export TF_VAR_workload_min_node_count := $(WORKLOAD_MIN_NODE_COUNT)
export TF_VAR_workload_max_node_count := $(WORKLOAD_MAX_NODE_COUNT)
export TF_VAR_workload_machine_type := $(WORKLOAD_MACHINE_TYPE)
export TF_VAR_workload_disk_size_gb := $(WORKLOAD_DISK_SIZE_GB)
export TF_VAR_workload_disk_type := $(WORKLOAD_DISK_TYPE)

help:
	@echo "Targets:"
	@echo "  tf-init                  Terraform init"
	@echo "  tf-plan                  Terraform plan"
	@echo "  tf-apply                 Terraform apply"
	@echo "  tf-destroy               Terraform destroy"
	@echo "  gke-credentials          Refresh kubectl credentials for the target cluster"
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
	terraform -chdir=$(TF_DIR) init $(TF_ARGS)

tf-plan:
	terraform -chdir=$(TF_DIR) plan $(TF_ARGS)

tf-apply:
	terraform -chdir=$(TF_DIR) apply $(TF_ARGS)

tf-destroy:
	terraform -chdir=$(TF_DIR) destroy $(TF_ARGS)

gke-credentials:
	gcloud container clusters get-credentials "$(CLUSTER_NAME)" --region "$(REGION)" --project "$(PROJECT_ID)"

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
