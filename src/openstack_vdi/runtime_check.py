"""Offline smoke check executed by the built application, not the build interpreter."""

from keystoneauth1.session import Session
from openstack.connection import Connection


def check_package_runtime() -> None:
    # Connection construction loads dogpile's cache backend dynamically. A successful
    # GUI startup does not exercise that path, and PyInstaller cannot infer the import.
    connection = Connection(session=Session(), region_name="RegionOne")
    connection.close()
