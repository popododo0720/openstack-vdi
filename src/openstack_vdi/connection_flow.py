"""A cancellable, bounded connect intent, independent of widgets and transport."""

from __future__ import annotations

import time
from dataclasses import dataclass

from .models import Desktop


@dataclass
class ConnectIntent:
    desktop_id: str
    deadline: float
    old_boot: str = ""
    require_new_boot: bool = False
    started: bool = False

    @classmethod
    def begin(cls, desktop: Desktop, reboot=False, now=None):
        return cls(
            desktop.id, (time.monotonic() if now is None else now) + 300, desktop.boot_id, reboot
        )

    def step(self, desktop: Desktop | None, now=None):
        now = time.monotonic() if now is None else now
        if now >= self.deadline:
            return "timeout"
        if desktop is None:
            return "missing"
        if desktop.status == "ERROR":
            return "error"
        if desktop.task_state:
            return "wait"
        if desktop.status == "SHUTOFF" and not self.started and not self.require_new_boot:
            self.started = True
            return "start"
        if desktop.status != "ACTIVE":
            return "wait"
        if self.require_new_boot and (not desktop.boot_id or desktop.boot_id == self.old_boot):
            return "wait"
        if desktop.ready is False:
            return "wait"
        # Legacy direct mode cannot prove guest readiness; no automatic reboot reconnect there.
        return "connect"
