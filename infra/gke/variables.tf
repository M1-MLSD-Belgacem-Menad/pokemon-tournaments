variable "project_id" {
  description = "Identifiant du projet Google Cloud (pas son nom)"
  type        = string
}

variable "zone" {
  description = "Zone du cluster"
  type        = string
  default     = "europe-west1-b"
}

variable "machine_type" {
  description = "Type des nœuds : 2 vCPU partagés et 4 Go par nœud"
  type        = string
  default     = "e2-medium"
}

variable "node_count" {
  description = "Nombre de nœuds : avec 2, les pods système de GKE laissent des pods de l'application en Pending faute de CPU"
  type        = number
  default     = 3
}
