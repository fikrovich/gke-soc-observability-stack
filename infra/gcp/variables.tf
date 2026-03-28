variable "project_id" {
  type    = string
  default = "example-observability"
}

variable "region" {
  type    = string
  default = "example-region-1"
}

variable "cluster_name" {
  type    = string
  default = "observability-cluster"
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
