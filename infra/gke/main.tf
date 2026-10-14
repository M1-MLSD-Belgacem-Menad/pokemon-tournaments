# Cluster GKE pour le palier « cloud » : mêmes manifestes que minikube (k8s/), seul le cluster change.
# Usage et coût : README, section « Déploiement sur GKE ».

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.6.0" # correctifs seulement : même version en CI et sur le PC
    }
  }
}

provider "google" {
  project = var.project_id
  # Avec les identifiants de `gcloud auth application-default login`, les quotas des API
  # (dont l'activation de container.googleapis.com) sont comptés sur ce projet.
  billing_project       = var.project_id
  user_project_override = true
}

resource "google_project_service" "container" {
  service            = "container.googleapis.com"
  disable_on_destroy = false
}

# Cluster zonal : un seul plan de contrôle, couvert par le crédit mensuel gratuit de GKE.
resource "google_container_cluster" "pokemon" {
  name                = "pokemon"
  location            = var.zone
  deletion_protection = false # `terraform destroy` doit pouvoir le supprimer

  # Dataplane V2 applique les NetworkPolicy de k8s/network-policies.yaml (rôle de Calico sur minikube).
  datapath_provider = "ADVANCED_DATAPATH"

  # Les nœuds sont dans le pool ci-dessous : changer leur nombre ne recrée pas le cluster.
  remove_default_node_pool = true
  initial_node_count       = 1

  depends_on = [google_project_service.container]
}

resource "google_container_node_pool" "nodes" {
  name       = "nodes"
  cluster    = google_container_cluster.pokemon.name
  location   = var.zone
  node_count = var.node_count

  node_config {
    machine_type = var.machine_type
    disk_type    = "pd-standard"
    disk_size_gb = 30
  }
}
