"""Build on the target OS: Windows builds .exe, Linux builds a native executable."""

import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
command = [
    sys.executable,
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--onedir",
    "--name",
    "OpenStackVDI",
    "--collect-submodules",
    "openstack.compute",
    "--collect-submodules",
    "openstack.identity",
    "--collect-data",
    "openstack",
    "--collect-submodules",
    "keystoneauth1.identity",
    "--hidden-import",
    "dogpile.cache.backends.null",
    "--hidden-import",
    "dogpile.cache.backends.memory",
    "--exclude-module",
    "openstack.tests",
    "--exclude-module",
    "openstack.test",
    "--exclude-module",
    "openstack.fixture",
    "--exclude-module",
    "keystoneauth1.tests",
    "--exclude-module",
    "keystoneauth1.fixture",
    "--collect-data",
    "os_service_types",
    "--copy-metadata",
    "openstacksdk",
    "--copy-metadata",
    "keystoneauth1",
    "--copy-metadata",
    "os-service-types",
    "--copy-metadata",
    "dogpile.cache",
    "--copy-metadata",
    "stevedore",
    "--copy-metadata",
    "PySide6-Essentials",
    "--copy-metadata",
    "shiboken6",
    "--add-data",
    f"{root / 'LICENSE'}:.",
    "--add-data",
    f"{root / 'THIRD_PARTY_NOTICES.md'}:.",
    str(root / "scripts" / "launcher.py"),
]
subprocess.run(command, cwd=root, check=True)
executable = (
    root
    / "dist"
    / "OpenStackVDI"
    / ("OpenStackVDI.exe" if sys.platform == "win32" else "OpenStackVDI")
)
subprocess.run([str(executable), "--check-package"], cwd=root, check=True, timeout=60)
