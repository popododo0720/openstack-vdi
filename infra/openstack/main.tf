data "openstack_networking_network_v2" "external" {
  name     = var.external_network_name
  external = true
}

resource "openstack_networking_network_v2" "vdi" {
  name           = "${var.name}-net"
  admin_state_up = true
  description    = "OpenStack VDI PoC network"
}

resource "openstack_networking_subnet_v2" "vdi" {
  name            = "${var.name}-subnet"
  network_id      = openstack_networking_network_v2.vdi.id
  cidr            = var.subnet_cidr
  ip_version      = 4
  enable_dhcp     = true
  dns_nameservers = var.dns_nameservers
}

resource "openstack_networking_router_v2" "vdi" {
  name                = "${var.name}-router"
  admin_state_up      = true
  external_network_id = data.openstack_networking_network_v2.external.id
}

resource "openstack_networking_router_interface_v2" "vdi" {
  router_id = openstack_networking_router_v2.vdi.id
  subnet_id = openstack_networking_subnet_v2.vdi.id
}

resource "openstack_networking_secgroup_v2" "server" {
  name        = "${var.name}-sg"
  description = "SSH and native RustDesk only; no web console"
}

resource "openstack_networking_secgroup_rule_v2" "ssh" {
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 22
  port_range_max    = 22
  remote_ip_prefix  = var.admin_cidr
  security_group_id = openstack_networking_secgroup_v2.server.id
}

locals {
  native_sources = setunion(var.client_cidrs, toset([var.subnet_cidr]))
}

resource "openstack_networking_secgroup_rule_v2" "native_tcp" {
  for_each          = local.native_sources
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 21115
  port_range_max    = 21117
  remote_ip_prefix  = each.value
  security_group_id = openstack_networking_secgroup_v2.server.id
}

resource "openstack_networking_secgroup_rule_v2" "native_udp" {
  for_each          = local.native_sources
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "udp"
  port_range_min    = 21116
  port_range_max    = 21116
  remote_ip_prefix  = each.value
  security_group_id = openstack_networking_secgroup_v2.server.id
}

resource "openstack_networking_port_v2" "server" {
  name               = "${var.name}-port"
  network_id         = openstack_networking_network_v2.vdi.id
  admin_state_up     = true
  security_group_ids = [openstack_networking_secgroup_v2.server.id]
  fixed_ip {
    subnet_id = openstack_networking_subnet_v2.vdi.id
  }
}

resource "openstack_networking_floatingip_v2" "server" {
  pool        = var.external_network_name
  description = "OpenStack VDI PoC server"
}

resource "openstack_compute_keypair_v2" "server" {
  name       = "${var.name}-key"
  public_key = var.ssh_public_key
}

resource "openstack_compute_instance_v2" "server" {
  name         = var.name
  flavor_id    = var.flavor_id
  key_pair     = openstack_compute_keypair_v2.server.name
  config_drive = true
  metadata = {
    managed_by = "openstack-vdi"
    purpose    = "rustdesk-id-relay"
  }

  block_device {
    uuid                  = var.ubuntu_image_id
    source_type           = "image"
    destination_type      = "volume"
    volume_size           = var.root_disk_gb
    boot_index            = 0
    delete_on_termination = true
  }

  network {
    port = openstack_networking_port_v2.server.id
  }

  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    advertise_host = openstack_networking_floatingip_v2.server.address
    compose        = indent(6, file("${path.module}/../server/compose.yaml"))
    start_script   = indent(6, file("${path.module}/../server/start-server.sh"))
    service        = indent(6, file("${path.module}/../server/openstack-vdi-server.service"))
  })

  depends_on = [openstack_networking_router_interface_v2.vdi]
}

resource "openstack_networking_floatingip_associate_v2" "server" {
  floating_ip = openstack_networking_floatingip_v2.server.address
  port_id     = openstack_networking_port_v2.server.id
  depends_on  = [openstack_compute_instance_v2.server]
}

