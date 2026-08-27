
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
