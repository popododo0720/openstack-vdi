from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt

from openstack_vdi.app import MainWindow
from openstack_vdi.backend import DemoBackend
from openstack_vdi.models import Desktop, LoginSession
from openstack_vdi.settings import SettingsStore


@pytest.fixture
def window(qtbot, tmp_path):
    window = MainWindow(settings=SettingsStore(tmp_path / "settings.json"), demo=True)
    qtbot.addWidget(window, before_close_func=lambda w: w.remote.close())
    window.show()
    qtbot.waitUntil(lambda: len(window.desktops) == 2 and not window._busy)
    window.timer.stop()
    yield window
    window.remote.close()
    qtbot.waitUntil(lambda: not window._busy)


def test_demo_select_start_refresh_and_reconnect_without_launching(qtbot, window):
    assert window.pages.currentIndex() == 1
    assert not window.buttons["start"].isEnabled()
    assert window.connect_button.isEnabled()
    window.table.selectRow(1)
    assert window.buttons["start"].isEnabled()
    assert window.connect_button.isEnabled()
    qtbot.mouseClick(window.buttons["start"], Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window._busy)
    assert not window.connect_button.isEnabled()
    # The simulated VM is asynchronously booting. Finish the clock without sleeping.
    window.backend._pending["demo-private"] = (0, "ACTIVE")
    window.refresh()
    qtbot.waitUntil(lambda: not window._busy)
    assert window.selected().id == "demo-private"
    assert window.connect_button.isEnabled()
    with patch("openstack_vdi.native_session.launch_rustdesk") as launch:
        qtbot.mouseClick(window.connect_button, Qt.MouseButton.LeftButton)
        launch.assert_not_called()
    assert "데모 모드" in window.statusBar().currentMessage()


def test_stop_requires_confirmation_and_cancel_preserves_vm(qtbot, window):
    with patch("openstack_vdi.app.confirm", return_value=False):
        qtbot.mouseClick(window.buttons["stop"], Qt.MouseButton.LeftButton)
    assert window.backend._pending == {}
    with patch("openstack_vdi.app.confirm", return_value=True):
        qtbot.mouseClick(window.buttons["stop"], Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window._busy)
    assert window.backend._pending["demo-work"][1] == "SHUTOFF"


def test_refresh_failure_disables_stale_power_and_connection_controls(qtbot, window):
    with patch.object(window.backend, "list_desktops", side_effect=RuntimeError("SECRET")):
        window.refresh()
        qtbot.waitUntil(lambda: not window._busy)
    assert not window.connect_button.isEnabled()
    assert not window.buttons["stop"].isEnabled()
    assert "SECRET" not in window.notice.text()
    window.refresh()
    qtbot.waitUntil(lambda: not window._busy)
    assert window.connect_button.isEnabled()


def test_empty_project_does_not_offer_actions(window):
    window._show_desktops([])
    assert "배정된 PC가 없습니다" in window.count.text()
    assert not window.connect_button.isEnabled()
    assert not window.peer_button.isEnabled()


def test_real_connect_uses_selected_project_mapping_not_ip(window):
    window.demo = False
    window.settings.save_peer_id("demo", "demo-work", "123456789")
    with patch("openstack_vdi.native_session.launch_rustdesk") as launch:
        window.connect_desktop()
        launch.assert_called_once_with("123456789", "")


def test_logout_clears_desktops_and_session(qtbot, window):
    window.logout()
    qtbot.waitUntil(lambda: not window._busy)
    assert window.session is None
    assert window.desktops == []
    assert window.pages.currentIndex() == 0


def test_login_clears_password_even_when_authentication_fails(qtbot, tmp_path):
    backend = DemoBackend()
    window = MainWindow(backend=backend, settings=SettingsStore(tmp_path / "settings.json"))
    qtbot.addWidget(window, before_close_func=lambda w: w.remote.close())
    window.fields["auth_url"].setText("https://example.org/v3")
    window.fields["username"].setText("alice")
    window.fields["project_name"].setText("alice")
    window.fields["password"].setText("SECRET")
    with patch.object(backend, "login", side_effect=RuntimeError("SECRET")):
        window.login()
        qtbot.waitUntil(lambda: not window._busy)
    assert window.fields["password"].text() == ""
    assert "SECRET" not in window.login_error.text()
    assert not (tmp_path / "settings.json").exists()


def test_server_names_are_rendered_as_plain_text(window):
    window.session = LoginSession("alice", "project", "id", "scope")
    name = '<a href="https://evil">Name</a>'
    window._show_desktops([Desktop("id", name, "ACTIVE")])
    assert window.table.item(0, 0).text() == name


def test_refresh_keeps_buttons_live_and_queues_power_click(qtbot, window):
    import threading

    gate = threading.Event()
    original = window.backend.list_desktops

    def slow_list():
        assert gate.wait(3)
        return original()

    with patch.object(window.backend, "list_desktops", side_effect=slow_list):
        window.refresh()
        assert window.connect_button.isEnabled()
        with patch("openstack_vdi.app.confirm", return_value=True):
            window.power("stop")
        assert window._queued is not None
        gate.set()
        qtbot.waitUntil(lambda: not window._busy and window._queued is None)
    assert window.backend._pending["demo-work"][1] == "SHUTOFF"


def test_cancel_pending_guest_wait_never_opens_remote(window):
    from dataclasses import replace

    window.demo = False
    window.settings.save_peer_id("demo", "demo-work", "123456789")
    window._show_desktops([replace(window.desktops[0], ready=False)])
    with patch.object(window.remote, "open") as launch:
        window.connect_desktop()
        assert window.intent is not None
        window.cancel_connect()
        window._show_desktops([replace(window.desktops[0], ready=True)])
        launch.assert_not_called()


def test_cancel_inflight_authorization_does_not_launch_late_result(qtbot, window):
    import threading
    from dataclasses import replace

    from openstack_vdi.broker_client import BrokerBackend

    backend = BrokerBackend()
    gate = threading.Event()
    window.backend = backend
    window.demo = False
    window._show_desktops([replace(window.desktops[0], ready=True, peer_id="123456789")])

    def authorize(_):
        assert gate.wait(3)
        return "123456789"

    with (
        patch.object(backend, "connection_peer", side_effect=authorize),
        patch.object(window.remote, "open") as launch,
    ):
        window.connect_desktop()
        assert window._opening
        window.cancel_connect()
        gate.set()
        qtbot.waitUntil(lambda: not window._busy)
        launch.assert_not_called()


def test_external_disconnect_waits_out_stale_guest_heartbeat(window):
    import time
    from dataclasses import replace

    from openstack_vdi.broker_client import BrokerBackend

    window.backend = BrokerBackend()
    window.demo = False
    window._show_desktops([replace(window.desktops[0], ready=True, peer_id="123456789")])
    window._remote_id = window.desktops[0].id
    window.remote.peer = "123456789"
    window.remote.was_connected = True
    window.remote.reason = "network"
    with (
        patch.object(window.remote, "poll", return_value="disconnected"),
        patch.object(window.backend, "connection_peer") as authorize,
    ):
        window._poll_remote()
        assert window.intent is not None
        assert window._retry_at - time.monotonic() > 30
        window._advance_connect()
        authorize.assert_not_called()
    window.cancel_connect()
