variable "name" {
  type    = string
  default = "vdi-server-poc"
}

variable "ubuntu_image_id" {
  type        = string
  description = "Existing Ubuntu 24.04 cloud image UUID in Glance."
}

variable "flavor_id" {
  type        = string
  description = "Existing flavor UUID; start with 2 vCPU and 2-4 GiB RAM."
}

variable "external_network_name" {
  type        = string
  description = "Existing external/provider network name for router and floating IP."
}

variable "ssh_public_key" {
  type        = string
  description = "Public SSH key for the Ubuntu administrator (never a private key)."
  validation {
    condition     = can(regex("^(ssh-ed25519|ssh-rsa|ecdsa-sha2-)", var.ssh_public_key))
    error_message = "Provide an SSH public key."
  }
}

variable "admin_cidr" {
  type        = string
  description = "Source CIDR allowed to SSH into the server."
  validation {
    condition     = can(cidrhost(var.admin_cidr, 0)) && var.admin_cidr != "0.0.0.0/0"
    error_message = "Set a specific administrator CIDR, not the entire internet."
  }
}

variable "client_cidrs" {
  type        = set(string)
  description = "Networks allowed to connect native RustDesk clients."
  validation {
    condition = length(var.client_cidrs) > 0 && alltrue([
      for cidr in var.client_cidrs : can(cidrhost(cidr, 0)) && cidr != "0.0.0.0/0"
    ])
    error_message = "Set specific client CIDRs."
  }
}

variable "subnet_cidr" {
  type    = string
  default = "10.77.0.0/24"
}

variable "dns_nameservers" {
  type    = list(string)
  default = ["1.1.1.1", "8.8.8.8"]
}

variable "root_disk_gb" {
  type    = number
  default = 20
}

