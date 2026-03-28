provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_compute_network" "soc" {
  name                    = var.network_name
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "soc" {
  name          = var.subnet_name
  ip_cidr_range = var.subnet_cidr
  region        = var.region
  network       = google_compute_network.soc.id
}

resource "google_compute_router" "soc" {
  name    = "soc-router"
  region  = var.region
  network = google_compute_network.soc.id
}

resource "google_compute_router_nat" "soc" {
  name                               = "soc-nat"
  router                             = google_compute_router.soc.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}

resource "google_container_cluster" "soc" {
  name                     = var.cluster_name
  location                 = var.region
  network                  = google_compute_network.soc.name
  subnetwork               = google_compute_subnetwork.soc.name
  remove_default_node_pool = true
  initial_node_count       = 1

  release_channel {
    channel = "REGULAR"
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = var.master_ipv4_cidr
  }

  dynamic "master_authorized_networks_config" {
    for_each = length(var.authorized_networks) > 0 ? [1] : []
    content {
      dynamic "cidr_blocks" {
        for_each = var.authorized_networks
        content {
          display_name = cidr_blocks.value.display_name
          cidr_block   = cidr_blocks.value.cidr_block
        }
      }
    }
  }
}

resource "google_container_node_pool" "master" {
  name       = "pool-es-master-zone-a"
  location   = var.region
  cluster    = google_container_cluster.soc.name
  node_count = 3

  node_config {
    machine_type = "n2d-standard-2"
    disk_size_gb = 100
    disk_type    = "pd-ssd"
    labels = {
      elasticsearch.role        = "master"
      topology_kubernetes_io_zone = "example-region-1a"
    }
    taint {
      key    = "elasticsearch.role"
      value  = "master"
      effect = "NO_SCHEDULE"
    }
  }
}

resource "google_container_node_pool" "hot" {
  name     = "pool-es-hot-zone-a"
  location = var.region
  cluster  = google_container_cluster.soc.name

  autoscaling {
    min_node_count = 3
    max_node_count = 5
  }

  node_config {
    machine_type = "n2d-standard-8"
    disk_size_gb = 100
    disk_type    = "pd-ssd"
    labels = {
      elasticsearch.role = "data-hot"
      data               = "hot"
    }
    taint {
      key    = "elasticsearch.role"
      value  = "hot"
      effect = "NO_SCHEDULE"
    }
  }
}

resource "google_container_node_pool" "warm" {
  name     = "pool-es-warm-zone-a"
  location = var.region
  cluster  = google_container_cluster.soc.name

  autoscaling {
    min_node_count = 3
    max_node_count = 5
  }

  node_config {
    machine_type = "n2d-standard-4"
    disk_size_gb = 100
    disk_type    = "pd-standard"
    labels = {
      elasticsearch.role = "data-warm"
      data               = "warm"
    }
    taint {
      key    = "elasticsearch.role"
      value  = "warm"
      effect = "NO_SCHEDULE"
    }
  }
}

resource "google_container_node_pool" "workload" {
  name     = "pool-workload-zone-a"
  location = var.region
  cluster  = google_container_cluster.soc.name

  autoscaling {
    min_node_count = 4
    max_node_count = 12
  }

  node_config {
    machine_type = "n2d-standard-4"
    disk_size_gb = 100
    disk_type    = "pd-standard"
  }
}
