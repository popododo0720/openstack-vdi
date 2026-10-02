variable "enable_broker" {
  type        = bool
  default     = false
  description = "Allow HTTPS to the optional native-client assignment broker."
}

resource "openstack_networking_secgroup_rule_v2" "broker_https" {
  for_each          = var.enable_broker ? local.native_sources : toset([])
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 8443
  port_range_max    = 8443
  remote_ip_prefix  = each.value
  security_group_id = openstack_networking_secgroup_v2.server.id
}
