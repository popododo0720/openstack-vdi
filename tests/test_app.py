from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from openstack_vdi.app import MainWindow
from openstack_vdi.backend import DemoBackend
from openstack_vdi.models import Desktop, LoginSession
from openstack_vdi.settings import SettingsStore


@pytest.fixture
def window(qtbot, tmp_path):
    window = MainWindow(settings=SettingsStore(tmp_path / "settings.json"), demo=True)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: len(window.desktops) == 2 and not window._busy)
    window.timer.stop()
    yield window
    qtbot.waitUntil(lambda: not window._busy)


def test_demo_select_start_refresh_and_reconnect_without_launching(qtbot, window):
    assert window.pages.currentIndex() == 1
    assert not window.buttons["start"].isEnabled()
    assert window.connect_button.isEnabled()
    window.table.selectRow(1)
    assert window.buttons["start"].isEnabled()
    assert not window.connect_button.isEnabled()
    qtbot.mouseClick(window.buttons["start"], Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window._busy)
    assert not window.connect_button.isEnabled()
    # The simulated VM is asynchronously booting. Finish the clock without sleeping.
    window.backend._pending["demo-private"] = (0, "ACTIVE")
    window.refresh()
    qtbot.waitUntil(lambda: not window._busy)
    assert window.selected().id == "demo-private"
    assert window.connect_button.isEnabled()
    with patch("openstack_vdi.app.launch_rustdesk") as launch:
        qtbot.mouseClick(window.connect_button, Qt.MouseButton.LeftButton)
        launch.assert_not_called()
    assert "데모 모드" in window.statusBar().currentMessage()


def test_stop_requires_confirmation_and_cancel_preserves_vm(qtbot, window):
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
        qtbot.mouseClick(window.buttons["stop"], Qt.MouseButton.LeftButton)
    assert window.backend._pending == {}
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
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
    assert "VM이 없습니다" in window.count.text()
    assert not window.connect_button.isEnabled()
    assert not window.peer_button.isEnabled()


def test_real_connect_uses_selected_project_mapping_not_ip(window):
    window.demo = False
    window.settings.save_peer_id("demo", "demo-work", "123456789")
    with patch("openstack_vdi.app.launch_rustdesk") as launch:
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
    qtbot.addWidget(window)
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
