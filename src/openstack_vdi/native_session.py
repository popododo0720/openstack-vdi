"""Windows window ownership and a conservative RustDesk 1.4.9 log observer.

Log evidence belongs to the currently launched connection only. Missing/unknown log
formats never imply a connected session. No passwords are parsed or persisted.
"""

from __future__ import annotations

import ctypes
import os
import re
import time
from pathlib import Path

from .remote import launch_rustdesk, validate_peer_id


def peer_windows(peer_id):
    if os.name != "nt":
        return []
    from ctypes import wintypes as w

    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [
        w.HANDLE,
        w.DWORD,
        w.LPWSTR,
        ctypes.POINTER(w.DWORD),
    ]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    user.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    user.IsWindowVisible.argtypes = [w.HWND]
    callback = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    found = []

    def inspect(hwnd, _):
        title = ctypes.create_unicode_buffer(2048)
        user.GetWindowTextW(hwnd, title, len(title))
        if not user.IsWindowVisible(hwnd) or not re.search(
            rf"(?<![\w-]){re.escape(peer_id)}(?![\w-])", title.value
        ):
            return True
        pid = w.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel.OpenProcess(0x1000, False, pid.value)
        if handle:
            try:
                path, length = ctypes.create_unicode_buffer(32768), w.DWORD(32768)
                if kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(length)):
                    if Path(path.value).name.casefold() == "rustdesk.exe":
                        found.append(hwnd)
            finally:
                kernel.CloseHandle(handle)
        return True

    user.EnumWindows.argtypes = [callback, w.LPARAM]
    user.EnumWindows(callback(inspect), 0)
    return found


def focus_peer(peer_id):
    windows = peer_windows(peer_id)
    if not windows:
        return False
    from ctypes import wintypes as w

    user = ctypes.WinDLL("user32", use_last_error=True)
    user.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
    user.SetForegroundWindow.argtypes = [w.HWND]
    user.ShowWindow(windows[0], 9)
    user.SetForegroundWindow(windows[0])
    return True


def close_peer(peer_id):
    if os.name == "nt":
        from ctypes import wintypes as w

        user = ctypes.WinDLL("user32", use_last_error=True)
        user.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
        for hwnd in peer_windows(peer_id):
            user.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE; never stop the RustDesk service.


class NativeSession:
    def __init__(self, log_root=None):
        self.log_root = log_root or Path(os.environ.get("APPDATA", "")) / "RustDesk/log/flutter_ffi"
        self.peer = ""
        self.state = "closed"
        self.offsets = {}
        self.started = 0.0
        self.seen_window = False
        self.was_connected = False
        self.reason = ""

    def _files(self):
        return list(self.log_root.glob("*.log")) if os.name == "nt" else []

    def open(self, peer, executable=""):
        peer = validate_peer_id(peer)
        if focus_peer(peer):
            return "existing"
        if (
            self.peer == peer
            and self.state in ("opening", "authenticating")
            and time.monotonic() - self.started < 15
        ):
            return "existing"
        self.offsets = {str(p): (p.stat().st_ino, p.stat().st_size) for p in self._files()}
        self.peer, self.state, self.started = peer, "opening", time.monotonic()
        self.seen_window = self.was_connected = False
        self.reason = ""
        launch_rustdesk(peer, executable)
        return "opened"

    def close(self):
        if self.peer:
            close_peer(self.peer)
        self.peer, self.state = "", "closed"

    def consume(self, text):
        # Only known markers. Never relay raw logs (addresses and names can be sensitive).
        for line in text.splitlines():
            if "peer info supported_encoding:" in line:
                self.state = "authenticating"
            elif "new video handler for display" in line:
                self.state, self.was_connected = "connected", True
            elif "Connection closed:" in line or f"Exit io_loop of id={self.peer}" in line:
                self.state = "disconnected"
                self.reason = "offline" if "offline" in line.lower() else "network"
                if "password" in line.lower() or "authentication" in line.lower():
                    self.reason = "authentication"

    def poll(self):
        if not self.peer or os.name != "nt":
            return self.state
        windows = peer_windows(self.peer)
        if windows:
            self.seen_window = True
        elif self.seen_window:
            self.peer, self.state = "", "closed"
            return self.state
        for path in self._files():
            try:
                stat = path.stat()
                inode, offset = self.offsets.get(str(path), (stat.st_ino, 0))
                if inode != stat.st_ino or stat.st_size < offset:
                    offset = 0
                # Old files renamed by rotation are never interpreted as new session evidence.
                if (
                    str(path) not in self.offsets
                    and stat.st_mtime < time.time() - (time.monotonic() - self.started) - 1
                ):
                    self.offsets[str(path)] = stat.st_ino, stat.st_size
                    continue
                with path.open("rb") as stream:
                    stream.seek(offset)
                    data = stream.read(256 * 1024)
                    self.offsets[str(path)] = stat.st_ino, stream.tell()
                self.consume(data.decode("utf-8", errors="replace"))
            except OSError:
                continue
        return self.state
