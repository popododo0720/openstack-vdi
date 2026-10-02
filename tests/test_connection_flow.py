from dataclasses import replace

from openstack_vdi.connection_flow import ConnectIntent
from openstack_vdi.models import Desktop


def test_start_once_then_wait_for_guest_ready():
    vm = Desktop("vm", "Work", "SHUTOFF", ready=False)
    flow = ConnectIntent.begin(vm, now=0)
    assert flow.step(vm, now=1) == "start"
    assert flow.step(vm, now=2) == "wait"
    assert flow.step(replace(vm, status="ACTIVE"), now=3) == "wait"
    assert flow.step(replace(vm, status="ACTIVE", ready=True), now=4) == "connect"


def test_reboot_does_not_reconnect_to_old_boot_or_stale_heartbeat():
    vm = Desktop("vm", "Work", "ACTIVE", ready=True, boot_id="old")
    flow = ConnectIntent.begin(vm, reboot=True, now=0)
    assert flow.step(vm, now=1) == "wait"
    assert flow.step(replace(vm, boot_id="new", ready=False), now=2) == "wait"
    assert flow.step(replace(vm, boot_id="new"), now=3) == "connect"
    assert flow.step(vm, now=301) == "timeout"


def test_removed_or_failed_vm_never_connects():
    vm = Desktop("vm", "Work", "ERROR")
    flow = ConnectIntent.begin(vm, now=0)
    assert flow.step(None, now=1) == "missing"
    assert flow.step(vm, now=1) == "error"
