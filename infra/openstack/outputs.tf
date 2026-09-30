output "server_id" {
  value = openstack_compute_instance_v2.server.id
}

output "server_ip" {
  value = openstack_networking_floatingip_v2.server.address
}

output "desktop_network_id" {
  value = openstack_networking_network_v2.vdi.id
}

output "ssh_command" {
  value = "ssh ubuntu@${openstack_networking_floatingip_v2.server.address}"
}

output "public_key_command" {
  value = "ssh ubuntu@${openstack_networking_floatingip_v2.server.address} sudo cat /var/lib/openstack-vdi/rustdesk/id_ed25519.pub"
}

