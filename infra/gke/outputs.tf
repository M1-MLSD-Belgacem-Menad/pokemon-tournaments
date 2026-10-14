output "kubectl_credentials" {
  description = "Commande qui configure kubectl pour ce cluster"
  value       = "gcloud container clusters get-credentials ${google_container_cluster.pokemon.name} --zone ${var.zone} --project ${var.project_id}"
}
