output "cluster_name" {
  value = google_container_cluster.soc.name
}

output "cluster_region" {
  value = google_container_cluster.soc.location
}

output "network_name" {
  value = google_compute_network.soc.name
}

output "subnetwork_name" {
  value = google_compute_subnetwork.soc.name
}
