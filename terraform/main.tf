
data "sops_file" "flux_secret" {
  source_file = "${path.module}/cloud-init/30-flux-secret.sops.yaml"
}
data "sops_file" "sops_secret" {
  source_file = "${path.module}/cloud-init/40-sops-secret.sops.yaml"
}


locals {
  cloud_init_base = yamldecode(
    file("${path.module}/cloud-init/00-base.yaml")
  )

  cloud_init_files = yamldecode(
    file("${path.module}/cloud-init/10-files.yaml")
  )

  cloud_init_k3s = yamldecode(
    file("${path.module}/cloud-init/20-k3s-bootstrap.yaml")
  )

  cloud_init_flux_secret = yamldecode(
    data.sops_file.flux_secret.raw
  )

  cloud_init_sops_secret = yamldecode(
    data.sops_file.sops_secret.raw
  )

  cloud_init_runtime = yamldecode(
    file("${path.module}/cloud-init/90-runtime.yaml")
  )

  cloud_init = merge(
    local.cloud_init_base,
    local.cloud_init_runtime,
    {
      write_files = concat(
        try(local.cloud_init_files.write_files, []),
        try(local.cloud_init_k3s.write_files, []),
        try(local.cloud_init_flux_secret.write_files, []),
        try(local.cloud_init_sops_secret.write_files, [])
      )
    }
  )

  cloud_init_yaml = join("\n", [
    "#cloud-config",
    yamlencode(local.cloud_init),
  ])

}


resource "proxmox_download_file" "vm_image" {
  content_type = "import"
  datastore_id = "local"
  file_name    = "debian-13-generic-amd64-20260819-2575.qcow2"
  node_name    = "pvemini"
  url          = "http://cloud.debian.org/images/cloud/trixie/20260819-2575/debian-13-generic-amd64-20260819-2575.qcow2"
  overwrite    = false
  #decompression_algorithm = "zst"
}

resource "proxmox_virtual_environment_file" "cloudconfig" {
  content_type = "snippets"
  datastore_id = "local"
  node_name    = "pvemini"
  source_raw {
    #data      = file("${path.module}/cloud-config.yaml")
    data      = local.cloud_init_yaml
    file_name = "kubesat0-config.yaml"
  }
}


resource "proxmox_virtual_environment_vm" "vm" {
  name      = "kubesat0"
  node_name = "pvemini"

  # should be true if qemu agent is not installed / enabled on the VM
  stop_on_destroy = true

  disk {
    datastore_id = "local-lvm"
    import_from  = proxmox_download_file.vm_image.id
    interface    = "virtio0"
    iothread     = true
    discard      = "on"
    size         = 30
  }

  agent {
    enabled = true
  }

  cpu {
    cores = 2
    type  = "x86-64-v2-AES"
  }

  network_device {
    bridge = "vmbr0"
  }

  memory {
    dedicated = 3072
    floating  = 3072
  }


  initialization {

    user_data_file_id = proxmox_virtual_environment_file.cloudconfig.id

    user_account {
      # do not use this in production, configure your own ssh key instead!
      username = "debian"
    }

    dns {
      domain  = ".lan"
      servers = ["192.168.2.1"]
    }

    ip_config {
      ipv4 {
        address = "192.168.2.83/24"
        gateway = "192.168.2.1"
      }
    }
  }
}

output "vms_ipv4_address" {
  value = proxmox_virtual_environment_vm.vm.ipv4_addresses
}
