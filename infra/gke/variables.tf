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
  description = "Type des nœuds : 2 vCPU et 4 Go suffisent pour MySQL, les 3 services et ingress-nginx"
  type        = string
  default     = "e2-medium"
}

variable "node_count" {
  description = "Nombre de nœuds"
  type        = number
  default     = 2
}
