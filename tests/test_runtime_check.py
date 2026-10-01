from keystoneauth1.session import Session

from openstack_vdi.runtime_check import check_package_runtime


def test_package_check_initializes_sdk_without_network(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("Package check must not make network requests")

    monkeypatch.setattr(Session, "request", no_network)
    check_package_runtime()
