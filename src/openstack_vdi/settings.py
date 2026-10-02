from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from platformdirs import user_config_path

from .models import CloudProfile, UserError


class SettingsStore:
    """Local preferences only. Never store OpenStack/RustDesk passwords or tokens."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or user_config_path("OpenStackVDI", appauthor=False) / "settings.json"
        self.warning = ""
        self._data: dict = {}
        try:
            if self.path.exists():
                if self.path.stat().st_size > 1024 * 1024:
                    raise ValueError("Settings too large")
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("Invalid settings")
                self._data = data
        except (ValueError, OSError):
            self.warning = "저장된 설정을 읽지 못해 기본 설정으로 시작했습니다."

    def profile(self) -> CloudProfile:
        machine = {}
        deployment = (
            Path(os.environ.get("PROGRAMDATA", "/etc")) / "OpenStackVDI" / "deployment.json"
        )
        try:
            if deployment.is_file() and deployment.stat().st_size < 65536:
                machine = json.loads(deployment.read_text(encoding="utf-8-sig")).get("profile", {})
        except (OSError, ValueError, AttributeError):
            self.warning = "회사 연결 설정을 읽지 못했습니다. 관리자에게 문의하세요."
        data = self._data.get("profile", {})
        if isinstance(machine, dict):
            data = machine | (data if isinstance(data, dict) else {})
            # Administrator-installed endpoint and CA override stale user preferences.
            for key in ("broker_url", "ca_file"):
                if machine.get(key):
                    data[key] = machine[key]
        if not isinstance(data, dict):
            data = {}
        fields = CloudProfile.__dataclass_fields__
        known = {k: v for k, v in data.items() if k in fields and isinstance(v, str)}
        return CloudProfile(**({"auth_url": "", "username": "", "project_name": ""} | known))

    def save_profile(self, profile: CloudProfile) -> None:
        self._data["profile"] = asdict(profile)
        self._save()

    @property
    def rustdesk_path(self) -> str:
        value = self._data.get("rustdesk_path", "")
        return value if isinstance(value, str) else ""

    def save_rustdesk_path(self, value: str) -> None:
        self._data["rustdesk_path"] = value
        self._save()

    def peer_id(self, scope: str, server_id: str) -> str:
        mapping = self._data.get("peers", {})
        scoped = mapping.get(scope, {}) if isinstance(mapping, dict) else {}
        value = scoped.get(server_id, "") if isinstance(scoped, dict) else ""
        return value if isinstance(value, str) else ""

    def save_peer_id(self, scope: str, server_id: str, peer_id: str) -> None:
        peers = self._data.get("peers")
        if not isinstance(peers, dict):
            peers = {}
        if not isinstance(peers.get(scope), dict):
            peers[scope] = {}
        peers[scope][server_id] = peer_id
        self._data["peers"] = peers
        self._save()

    def _save(self) -> None:
        temporary: str | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                delete=False,
            ) as output:
                temporary = output.name
                json.dump(self._data, output, ensure_ascii=False, indent=2)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            if temporary:
                Path(temporary).unlink(missing_ok=True)
            raise UserError(
                "설정을 저장하지 못했습니다. 설정 폴더의 쓰기 권한을 확인하세요."
            ) from error
