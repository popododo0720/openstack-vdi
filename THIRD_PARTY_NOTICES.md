# Third-party software

This project is licensed under AGPL-3.0-only; see LICENSE.
The versions used for a build are recorded in uv.lock.

The native launcher depends on these separately maintained projects:

| Project | License | Source |
| --- | --- | --- |
| Qt for Python / PySide6 / Shiboken6 | LGPL-3.0 / GPL alternatives, per component | https://code.qt.io/pyside/pyside-setup.git/ |
| Qt | LGPL-3.0 / GPL alternatives, per component | https://code.qt.io/qt/ |
| OpenStack SDK and Keystone auth | Apache-2.0 | https://opendev.org/openstack/ |
| platformdirs | MIT | https://github.com/tox-dev/platformdirs |
| PyInstaller (build tool and bootloader) | GPL-2.0-or-later with bootloader exception | https://github.com/pyinstaller/pyinstaller |

The onedir distribution keeps Qt shared libraries separate. Preserve included
license files, applicable notices, and corresponding-source access when distributing
a binary. This table is not an exhaustive dependency license inventory; consult the
installed packages and their license files for the complete locked dependency tree.

RustDesk is an independent program installed by the user. Its executable and code
are not included in this repository or build. The launcher starts it as a separate
process with a peer ID. RustDesk's own AGPL license and notices remain applicable:
https://github.com/rustdesk/rustdesk/blob/master/LICENCE

