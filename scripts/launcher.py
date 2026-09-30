"""PyInstaller entrypoint; keep it separate from package-relative imports."""

from openstack_vdi.app import main

raise SystemExit(main())
