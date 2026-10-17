terraform {
  required_version = ">= 1.6"

  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "0.109.0"
    }

    sops = {
      source  = "carlpett/sops"
      version = "~> 1.4"
    }

    cloudinit = {
      source  = "hashicorp/cloudinit"
      version = "~> 2.4"
    }
  }
}

provider "sops" {}

provider "cloudinit" {}

provider "proxmox" {
  endpoint = var.pve_endpoint
  username = var.pve_username
  password = var.pve_password
  insecure = ! var.pve_valid_cert
  ssh {
    agent = true
  }
}
