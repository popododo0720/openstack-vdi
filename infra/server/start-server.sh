#!/bin/sh
# Runs INSIDE the provisioned Ubuntu VM, never on the operator's workstation.
set -eu
cd /opt/openstack-vdi
install -d -m 0700 -o 10001 -g 10001 /var/lib/openstack-vdi/rustdesk
docker compose up -d hbbs
# Generate the key once with hbbs before starting hbbr against the same key.
attempt=0
while [ ! -s /var/lib/openstack-vdi/rustdesk/id_ed25519.pub ]; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    echo "RustDesk ID server did not generate a key. Inspect docker compose logs hbbs." >&2
    exit 1
  fi
  sleep 1
done
chmod 0600 /var/lib/openstack-vdi/rustdesk/id_ed25519
chmod 0644 /var/lib/openstack-vdi/rustdesk/id_ed25519.pub
docker compose up -d hbbr

