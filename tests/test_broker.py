import json
from dataclasses import replace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from openstack_vdi.broker.service import create_app
from openstack_vdi.models import Desktop


@pytest.fixture
def broker(tmp_path):
    config = {
        "assignments": {"alice-id": ["work"], "bob-id": []},
        "desktops": {
            "work": {"name": "업무용 PC", "peer_id": "123456789", "agent_token": "agent-secret"}
        },
    }
    path = tmp_path / "broker.json"
    path.write_text(json.dumps(config))
    backend = Mock()
    backend.list_desktops.return_value = [
        Desktop("work", "internal", "ACTIVE"),
        Desktop("other", "other", "ACTIVE"),
    ]
    now = [100.0]
    app = create_app(
        path,
        auth_fn=lambda cfg, user, pw: user + "-id",
        backend_factory=lambda cfg: backend,
        clock=lambda: now[0],
    )
    client = TestClient(app, raise_server_exceptions=False)
    return client, backend, path, now


def login(client, user="alice"):
    response = client.post("/login", json={"username": user, "password": "secret"})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["token"]}


def beat(client, boot="boot-1", ready=True):
    return client.post(
        "/agent/work/heartbeat",
        json={"boot_id": boot, "ready": ready},
        headers={"Authorization": "Bearer agent-secret"},
    )


def test_user_assignment_limits_list_and_all_actions(broker):
    client, backend, _, _ = broker
    alice, bob = login(client), login(client, "bob")
    assert [r["name"] for r in client.get("/desktops", headers=alice).json()] == ["업무용 PC"]
    assert client.get("/desktops", headers=bob).json() == []
    for headers, vm in ((alice, "other"), (bob, "work")):
        assert (
            client.post(
                f"/desktops/{vm}/power", json={"action": "stop"}, headers=headers
            ).status_code
            == 403
        )
        assert client.post(f"/desktops/{vm}/connect", headers=headers).status_code == 403
    backend.power.assert_not_called()


def test_heartbeat_expiry_and_reboot_require_new_boot(broker):
    client, backend, _, now = broker
    auth = login(client)
    assert not client.get("/desktops", headers=auth).json()[0]["ready"]
    assert beat(client).status_code == 200
    assert client.get("/desktops", headers=auth).json()[0]["ready"]
    assert (
        client.post("/desktops/work/power", json={"action": "reboot"}, headers=auth).status_code
        == 200
    )
    now[0] += 1
    beat(client)
    assert not client.get("/desktops", headers=auth).json()[0]["ready"]
    assert client.post("/desktops/work/connect", headers=auth).status_code == 409
    beat(client, "boot-2")
    assert client.get("/desktops", headers=auth).json()[0]["ready"]
    now[0] += 26
    assert not client.get("/desktops", headers=auth).json()[0]["ready"]
    backend.power.assert_called_once_with("work", "reboot")


def test_revocation_logout_expiry_and_bad_agent_token(broker):
    client, _, path, now = broker
    auth = login(client)
    assert (
        client.post(
            "/agent/work/heartbeat", json={"boot_id": "x", "ready": True}, headers=auth
        ).status_code
        == 403
    )
    config = json.loads(path.read_text())
    config["assignments"].pop("alice-id")
    path.write_text(json.dumps(config))
    assert client.get("/desktops", headers=auth).status_code == 403
    bob = login(client, "bob")
    client.post("/logout", headers=bob)
    assert client.get("/desktops", headers=bob).status_code == 401
    bob = login(client, "bob")
    now[0] += 8 * 3600 + 1
    assert client.get("/desktops", headers=bob).status_code == 401


def test_no_secrets_in_validation_or_upstream_errors(broker):
    client, backend, _, _ = broker
    auth = login(client)
    response = client.post("/login", json={"username": {}, "password": "SUPER_SECRET"})
    assert response.status_code == 422 and "SUPER_SECRET" not in response.text
    backend.list_desktops.side_effect = RuntimeError("SUPER_SECRET")
    response = client.get("/desktops", headers=auth)
    assert response.status_code == 503 and "SUPER_SECRET" not in response.text


def test_ready_never_overrides_cloud_power_state(broker):
    client, backend, _, _ = broker
    beat(client)
    backend.list_desktops.return_value = [
        replace(backend.list_desktops.return_value[0], status="SHUTOFF")
    ]
    assert not client.get("/desktops", headers=login(client)).json()[0]["ready"]
