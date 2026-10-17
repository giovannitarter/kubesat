
variable "pve_endpoint" {
  type = string
}

variable "pve_node" {
  type = string
}

variable "pve_valid_cert" {
  type = bool
}


variable "pve_username" {
  description = "Proxmox username"
  type        = string
  sensitive   = true
}

variable "pve_password" {
  description = "Proxmox password"
  type        = string
  sensitive   = true
}
