from __future__ import annotations

import time
from dataclasses import replace
from typing import Protocol

from keystoneauth1 import session as ks_session
from keystoneauth1.identity import v3
from openstack.connection import Connection

from .models import CloudProfile, Desktop, LoginSession, UserError


def safe_error(error: Exception) -> str:
    """Never display raw SDK exceptions: they may contain response bodies or credentials."""
    if isinstance(error, UserError):
        return str(error)
    status = getattr(error, "http_status", None) or getattr(error, "status_code", None)
    if status == 401:
        return "로그인 정보가 올바르지 않거나 세션이 만료됐습니다. 다시 로그인하세요."
    if status == 403:
        return "이 프로젝트 또는 작업에 대한 권한이 없습니다. 관리자에게 권한을 확인하세요."
    if status == 404:
        return "VM 또는 API 경로를 찾지 못했습니다. 주소를 확인하거나 목록을 새로고침하세요."
    if status == 409:
        return "VM이 다른 작업을 처리 중입니다. 잠시 후 다시 시도하세요."
    name = type(error).__name__.lower()
    if "ssl" in name or "certificate" in name:
        return "서버 인증서를 확인하지 못했습니다. 관리자가 제공한 CA 인증서를 선택하세요."
    if "timeout" in name or "connect" in name or "discovery" in name:
        return "OpenStack 서버에 연결하지 못했습니다. 주소, 네트워크, API 접속 경로를 확인하세요."
    return "요청을 처리하지 못했습니다. 연결 설정과 서버 상태를 확인한 뒤 다시 시도하세요."


class Backend(Protocol):
    session: LoginSession | None

    def login(self, profile: CloudProfile, password: str) -> LoginSession: ...
    def list_desktops(self) -> list[Desktop]: ...
    def power(self, server_id: str, action: str) -> None: ...
    def close(self) -> None: ...


class OpenStackBackend:
    """One explicit, project-scoped session. No clouds.yaml or ambient OS_* credentials."""

    def __init__(self) -> None:
        self.session: LoginSession | None = None
        self._connection: Connection | None = None

    def login(self, profile: CloudProfile, password: str) -> LoginSession:
        profile.validate()
        if not password:
            raise UserError("비밀번호를 입력하세요.")
        auth = v3.Password(
            auth_url=profile.identity_url,
            username=profile.username,
            password=password,
            project_name=profile.project_name,
            user_domain_name=profile.user_domain,
            project_domain_name=profile.project_domain,
        )
        session = ks_session.Session(auth=auth, verify=profile.ca_file or True, timeout=15)
        connection = Connection(
            session=session,
            region_name=profile.region_name or None,
            interface=profile.interface,
            connect_retries=0,
            status_code_retries=0,
        )
        try:
            access = auth.get_access(session)
            if not access.project_id or not access.project_scoped:
                raise UserError("프로젝트 범위의 인증이 필요합니다. 프로젝트를 확인하세요.")
        except Exception:
            connection.close()
            raise
        self.close()
        self._connection = connection
        self.session = LoginSession(
            profile.username,
            profile.project_name,
            access.project_id,
            profile.scope_key(access.project_id),
        )
        return self.session

    def _require_connection(self) -> Connection:
        if self._connection is None or self.session is None:
            raise UserError("먼저 로그인하세요.")
        return self._connection

    def _belongs_to_project(self, server) -> bool:
        return self.session is not None and server.project_id == self.session.project_id

    @staticmethod
    def _desktop(server) -> Desktop:
        addresses = tuple(
            item["addr"]
            for network in (server.addresses or {}).values()
            for item in network
            if item.get("addr")
        )
        return Desktop(
            id=server.id,
            name=server.name or server.id,
            status=server.status or "UNKNOWN",
            addresses=addresses,
            task_state=server.task_state,
        )

    def list_desktops(self) -> list[Desktop]:
        connection = self._require_connection()
        # Do not request all_projects/all_tenants, even for an administrative token.
        return sorted(
            (
                self._desktop(server)
                for server in connection.compute.servers(details=True)
                if self._belongs_to_project(server)
            ),
            key=lambda desktop: (desktop.name.casefold(), desktop.id),
        )

    def power(self, server_id: str, action: str) -> None:
        if action not in ("start", "stop", "reboot"):
            raise UserError("지원하지 않는 전원 작업입니다.")
        connection = self._require_connection()
        server = connection.compute.get_server(server_id)
        if not self._belongs_to_project(server):
            raise UserError("현재 프로젝트에 속한 VM만 관리할 수 있습니다.")
        if not self._desktop(server).allows(action):
            raise UserError(
                "현재 VM 상태에서는 이 작업을 실행할 수 없습니다. 목록을 새로고침하세요."
            )
        if action == "start":
            connection.compute.start_server(server)
        elif action == "stop":
            connection.compute.stop_server(server)
        else:
            connection.compute.reboot_server(server, reboot_type="SOFT")

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
        self._connection = None
        self.session = None


class DemoBackend:
    """Explicit simulation: never contacts a cloud or launches a remote connection."""

    def __init__(self) -> None:
        self.session: LoginSession | None = None
        self._desktops = {
            "demo-work": Desktop("demo-work", "업무 데스크톱", "ACTIVE", ("10.10.0.21",)),
            "demo-private": Desktop("demo-private", "폐쇄망 데스크톱", "SHUTOFF", ("10.20.0.21",)),
        }
        self._pending: dict[str, tuple[float, str]] = {}

    def login(self, profile: CloudProfile, password: str) -> LoginSession:
        self.session = LoginSession("demo", "VDI Demo", "demo", "demo")
        return self.session

    def list_desktops(self) -> list[Desktop]:
        for server_id, (deadline, status) in list(self._pending.items()):
            if time.monotonic() >= deadline:
                self._desktops[server_id] = replace(
                    self._desktops[server_id],
                    status=status,
                    task_state=None,
                )
                del self._pending[server_id]
        return list(self._desktops.values())

    def power(self, server_id: str, action: str) -> None:
        desktop = self._desktops[server_id]
        if action not in ("start", "stop", "reboot") or not desktop.allows(action):
            raise UserError("현재 VM 상태에서는 이 작업을 실행할 수 없습니다.")
        self._desktops[server_id] = replace(desktop, task_state=action)
        self._pending[server_id] = (
            time.monotonic() + 1,
            "SHUTOFF" if action == "stop" else "ACTIVE",
        )

    def close(self) -> None:
        self.session = None
