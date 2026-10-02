from unittest.mock import patch

from openstack_vdi.native_session import NativeSession


def test_process_launch_does_not_mean_connected_and_clicks_are_coalesced():
    session = NativeSession()
    with (
        patch("openstack_vdi.native_session.focus_peer", return_value=False),
        patch("openstack_vdi.native_session.launch_rustdesk") as launch,
    ):
        assert session.open("123456789") == "opened"
        assert session.state == "opening"
        assert session.open("123456789") == "existing"
        launch.assert_called_once()
    session.consume("unknown future log format")
    assert session.state == "opening"
    session.consume("INFO peer info supported_encoding:{}")
    assert session.state == "authenticating"
    session.consume("INFO new video handler for display #0, format:VP9")
    assert session.state == "connected"
    session.consume("ERROR Connection closed: reset")
    assert session.state == "disconnected"


def test_existing_window_is_focused_without_new_process():
    with (
        patch("openstack_vdi.native_session.focus_peer", return_value=True),
        patch("openstack_vdi.native_session.launch_rustdesk") as launch,
    ):
        assert NativeSession().open("123456789") == "existing"
        launch.assert_not_called()


def test_log_rotation_does_not_replay_previous_connection(tmp_path):
    from types import SimpleNamespace

    current = tmp_path / "current.log"
    current.write_text("INFO new video handler for display #0\n")
    session = NativeSession(log_root=tmp_path)
    with (
        patch("openstack_vdi.native_session.os", SimpleNamespace(name="nt")),
        patch("openstack_vdi.native_session.focus_peer", return_value=False),
        patch("openstack_vdi.native_session.peer_windows", return_value=[1]),
        patch("openstack_vdi.native_session.launch_rustdesk"),
    ):
        session.open("123456789")
        current.rename(tmp_path / "previous.log")
        current.write_text("INFO connecting\n")
        assert session.poll() == "opening"
        with current.open("a") as stream:
            stream.write("INFO new video handler for display #0\n")
        assert session.poll() == "connected"
