import hashlib
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from openstack_vdi import credentials
from openstack_vdi.models import CloudProfile, UserError
from openstack_vdi.updates import download_update


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows Credential Manager roundtrip")
def test_windows_credential_roundtrip_and_scope_isolation():
    a = CloudProfile("https://test.invalid/v3", "vdi-test", "one")
    b = CloudProfile("https://test.invalid/v3", "vdi-test", "two")
    try:
        credentials.save(a, "test-only-credential")
        assert credentials.read(a) == "test-only-credential"
        assert credentials.read(b) == ""
    finally:
        credentials.forget(a)
    assert credentials.read(a) == ""


def test_updater_rejects_cross_origin_and_corrupt_installer(tmp_path):
    backend = SimpleNamespace(url="https://broker.example:8443", verify=True, http=MagicMock())
    release = {"version": "99.0.0", "url": "https://attacker.example/setup.exe", "sha256": "0" * 64}
    with pytest.raises(UserError, match="HTTPS"):
        download_update(backend, release, tmp_path)
    backend.http.get.assert_not_called()
    release["url"] = backend.url + "/download/client"
    response = backend.http.get.return_value.__enter__.return_value
    response.status_code = 200
    response.iter_content.return_value = [b"corrupted installer"]
    with pytest.raises(UserError, match="검증에 실패"):
        download_update(backend, release, tmp_path)
    assert list(tmp_path.iterdir()) == []
    release["sha256"] = hashlib.sha256(b"corrupted installer").hexdigest()
    path = download_update(backend, release, tmp_path)
    assert path.read_bytes() == b"corrupted installer"
