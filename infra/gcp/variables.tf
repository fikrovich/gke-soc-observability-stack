variable "project_id" {
  type    = string
  default = "example-observability"
}

variable "access_token" {
  type      = string
  default   = ""
  sensitive = true
}

variable "region" {
  type    = string
  default = "example-region-1"
}

variable "cluster_name" {
  type    = string
  default = "observability-cluster"
}

variable "cluster_deletion_protection" {
  type    = bool
  default = false
}

variable "network_name" {
  type    = string
  default = "platform-net"
}

variable "subnet_name" {
  type    = string
  default = "platform-subnet"
}

variable "subnet_cidr" {
  type    = string
  default = "10.10.0.0/16"
}

variable "master_ipv4_cidr" {
  type    = string
  default = "172.16.0.0/28"
}

variable "authorized_networks" {
  type = list(object({
    display_name = string
    cidr_block   = string
  }))
  default = []
}

variable "router_name" {
  type    = string
  default = "platform-router"
}

variable "nat_name" {
  type    = string
  default = "platform-nat"
}

variable "master_node_count" {
  type    = number
  default = 3
}

variable "master_machine_type" {
  type    = string
  default = "n2d-standard-2"
}

variable "master_disk_size_gb" {
  type    = number
  default = 100
}

variable "master_disk_type" {
  type    = string
  default = "pd-ssd"
}

variable "hot_min_node_count" {
  type    = number
  default = 3
}

variable "hot_max_node_count" {
  type    = number
  default = 5
}

variable "hot_machine_type" {
  type    = string
  default = "n2d-standard-8"
}

variable "hot_disk_size_gb" {
  type    = number
  default = 100
}

variable "hot_disk_type" {
  type    = string
  default = "pd-ssd"
}

variable "warm_min_node_count" {
  type    = number
  default = 3
}

variable "warm_max_node_count" {
  type    = number
  default = 5
}

variable "warm_machine_type" {
  type    = string
  default = "n2d-standard-4"
}

variable "warm_disk_size_gb" {
  type    = number
  default = 100
}

variable "warm_disk_type" {
  type    = string
  default = "pd-standard"
}

variable "workload_min_node_count" {
  type    = number
  default = 4
}

variable "workload_max_node_count" {
  type    = number
  default = 12
}

variable "workload_machine_type" {
  type    = string
  default = "n2d-standard-4"
}

variable "workload_disk_size_gb" {
  type    = number
  default = 100
}

variable "workload_disk_type" {
  type    = string
  default = "pd-standard"
}
