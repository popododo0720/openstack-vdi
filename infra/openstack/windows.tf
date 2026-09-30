variable "windows_image_id" {
  type        = string
  default     = null
  description = "Optional private Windows image UUID; null skips the desktop VM."
}

variable "windows_flavor_id" {
  type        = string
  default     = null
  description = "Windows flavor UUID; recommended 4 vCPU / 8 GiB RAM."
}

variable "windows_disk_gb" {
  type    = number
  default = 80
}

resource "openstack_networking_secgroup_v2" "desktop" {
  count       = var.windows_image_id == null ? 0 : 1
  name        = "${var.name}-desktop-sg"
  description = "Desktop initiates RustDesk connections; no inbound RDP or admin ports"
}

resource "openstack_networking_port_v2" "desktop" {
  count              = var.windows_image_id == null ? 0 : 1
  name               = "${var.name}-desktop-port"
  network_id         = openstack_networking_network_v2.vdi.id
  security_group_ids = [openstack_networking_secgroup_v2.desktop[0].id]
  fixed_ip {
    subnet_id = openstack_networking_subnet_v2.vdi.id
  }
}

resource "openstack_compute_instance_v2" "desktop" {
  count        = var.windows_image_id == null ? 0 : 1
  name         = "windows-11-vdi-poc"
  flavor_id    = var.windows_flavor_id
  config_drive = true
  metadata = {
    managed_by = "openstack-vdi"
    purpose    = "windows-desktop-test"
  }
  block_device {
    uuid                  = var.windows_image_id
    source_type           = "image"
    destination_type      = "volume"
    volume_size           = var.windows_disk_gb
    boot_index            = 0
    delete_on_termination = true
  }
  network {
    port = openstack_networking_port_v2.desktop[0].id
  }
  lifecycle {
    precondition {
      condition     = var.windows_flavor_id != null
      error_message = "Set windows_flavor_id when enabling the Windows VM."
    }
  }
  depends_on = [openstack_networking_router_interface_v2.vdi]
}

output "windows_server_id" {
  value = try(openstack_compute_instance_v2.desktop[0].id, null)
}

output "windows_private_ip" {
  value = try(openstack_networking_port_v2.desktop[0].all_fixed_ips[0], null)
}
