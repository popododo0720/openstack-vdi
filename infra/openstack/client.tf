variable "enable_windows_client" {
  type        = bool
  default     = false
  description = "Create a separate Windows endpoint for testing the native launcher."
}

resource "openstack_networking_secgroup_v2" "client" {
  count       = var.enable_windows_client ? 1 : 0
  name        = "${var.name}-client-sg"
  description = "Prototype endpoint; outbound connections only, console access via OpenStack"
}

resource "openstack_networking_port_v2" "client" {
  count              = var.enable_windows_client ? 1 : 0
  name               = "${var.name}-client-port"
  network_id         = openstack_networking_network_v2.vdi.id
  security_group_ids = [openstack_networking_secgroup_v2.client[0].id]
  fixed_ip {
    subnet_id = openstack_networking_subnet_v2.vdi.id
  }
}

resource "openstack_compute_instance_v2" "client" {
  count        = var.enable_windows_client ? 1 : 0
  name         = "windows-11-vdi-client-poc"
  flavor_id    = var.windows_flavor_id
  config_drive = true
  metadata = {
    managed_by = "openstack-vdi"
    purpose    = "windows-client-test"
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
    port = openstack_networking_port_v2.client[0].id
  }
  lifecycle {
    precondition {
      condition     = var.windows_image_id != null && var.windows_flavor_id != null
      error_message = "Set windows_image_id and windows_flavor_id before enabling the client."
    }
  }
  depends_on = [openstack_networking_router_interface_v2.vdi]
}

output "windows_client_server_id" {
  value = try(openstack_compute_instance_v2.client[0].id, null)
}

output "windows_client_private_ip" {
  value = try(openstack_networking_port_v2.client[0].all_fixed_ips[0], null)
}
