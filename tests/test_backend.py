from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from openstack_vdi.backend import OpenStackBackend, safe_error
from openstack_vdi.models import CloudProfile, LoginSession, UserError


def server(id="vm-1", project="mine", status="ACTIVE", task=None):
    return SimpleNamespace(
        id=id,
        project_id=project,
        status=status,
        task_state=task,
        name=id,
        addresses={"private": [{"addr": "10.0.0.4"}]},
    )


@pytest.fixture
def backend():
    backend = OpenStackBackend()
    backend.session = LoginSession("user", "My project", "mine", "scope")
    backend._connection = MagicMock()
    return backend


def test_listing_filters_foreign_project_even_if_api_returns_it(backend):
    backend._connection.compute.servers.return_value = [server(), server("other", "theirs")]
    assert [d.id for d in backend.list_desktops()] == ["vm-1"]
    backend._connection.compute.servers.assert_called_once_with(details=True)


@pytest.mark.parametrize("action", ["start", "stop", "reboot"])
def test_foreign_project_never_receives_power_action(backend, action):
    backend._connection.compute.get_server.return_value = server(project="theirs")
    with pytest.raises(UserError, match="현재 프로젝트"):
        backend.power("foreign-id", action)
    for method in ("start_server", "stop_server", "reboot_server"):
        getattr(backend._connection.compute, method).assert_not_called()


@pytest.mark.parametrize(
    "action,status,task",
    [
        ("start", "ACTIVE", None),
        ("stop", "SHUTOFF", None),
        ("reboot", "ACTIVE", "rebooting"),
        ("stop", "ERROR", None),
    ],
)
def test_power_rechecks_current_state_instead_of_trusting_stale_ui(backend, action, status, task):
    backend._connection.compute.get_server.return_value = server(status=status, task=task)
    with pytest.raises(UserError):
        backend.power("vm-1", action)
    assert backend._connection.compute.method_calls == [
        ("get_server", ("vm-1",), {}),
    ]


@pytest.mark.parametrize(
    "action,status,method",
    [
        ("start", "SHUTOFF", "start_server"),
        ("stop", "ACTIVE", "stop_server"),
        ("reboot", "ACTIVE", "reboot_server"),
    ],
)
def test_allowed_power_operations(backend, action, status, method):
    vm = server(status=status)
    backend._connection.compute.get_server.return_value = vm
    backend.power("vm-1", action)
    expected = {"reboot_type": "SOFT"} if action == "reboot" else {}
    getattr(backend._connection.compute, method).assert_called_once_with(vm, **expected)


def test_sdk_error_cannot_leak_credentials_or_response_body():
    assert "SUPER_SECRET" not in safe_error(RuntimeError("password=SUPER_SECRET"))


def test_authentication_errors_are_actionable_without_raw_message():
    error = RuntimeError("SUPER_SECRET")
    error.http_status = 401
    assert "다시 로그인" in safe_error(error)
    assert "SUPER_SECRET" not in safe_error(error)


def test_profile_normalizes_identity_and_namespaces_mapping():
    profile = CloudProfile("https://cloud.example:5000/", "alice", "alice")
    profile.validate()
    assert profile.identity_url == "https://cloud.example:5000/v3"
    assert profile.scope_key("project-a") != profile.scope_key("project-b")
    assert profile.scope_key("project-a") != CloudProfile(
        "https://another.example/v3",
        "alice",
        "alice",
    ).scope_key("project-a")


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "https://user:secret@host/v3", "bad", "https://["]
)
def test_invalid_auth_urls_are_rejected(url):
    with pytest.raises(UserError):
        CloudProfile(url, "user", "project").validate()
