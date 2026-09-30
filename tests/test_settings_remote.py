import json
from unittest.mock import patch

import pytest

from openstack_vdi.models import CloudProfile, UserError
from openstack_vdi.remote import launch_rustdesk, validate_peer_id
from openstack_vdi.settings import SettingsStore


def test_preferences_roundtrip_without_credentials_and_with_project_isolation(tmp_path):
    path = tmp_path / "config" / "settings.json"
    store = SettingsStore(path)
    profile = CloudProfile("https://cloud/v3", "alice", "project-a")
    store.save_profile(profile)
    store.save_peer_id("cloud-a-project-a", "vm-1", "123456789")
    other = SettingsStore(path)
    assert other.profile() == profile
    assert other.peer_id("cloud-a-project-a", "vm-1") == "123456789"
    assert other.peer_id("cloud-b-project-b", "vm-1") == ""
    raw = json.loads(path.read_text())
    assert "password" not in raw["profile"]
    assert "token" not in path.read_text()


def test_corrupt_settings_start_with_recoverable_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("broken{")
    store = SettingsStore(path)
    assert store.warning
    assert store.profile().username == ""
    store.save_profile(CloudProfile("https://cloud/v3", "alice", "p"))
    assert SettingsStore(path).profile().username == "alice"


@pytest.mark.parametrize(
    "peer", ["--password", "123;rm", "rustdesk://123", "123/r", "", "id@other-server"]
)
def test_remote_id_cannot_inject_flags_commands_or_other_servers(peer):
    with pytest.raises(UserError):
        validate_peer_id(peer)


def test_remote_launch_uses_argument_array_and_no_password(tmp_path):
    executable = tmp_path / "RustDesk Client"
    executable.touch()
    executable.chmod(0o700)
    with patch("openstack_vdi.remote.subprocess.Popen") as run:
        launch_rustdesk("123 456 789", str(executable))
    assert run.call_args.args[0] == [str(executable), "--connect", "123456789"]
    assert run.call_args.kwargs["shell"] is False


def test_missing_remote_binary_is_actionable(tmp_path):
    with pytest.raises(UserError, match="실행 파일"):
        launch_rustdesk("123456789", str(tmp_path / "missing.exe"))
