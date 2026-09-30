from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


class UserError(Exception):
    """A safe, actionable message that can be displayed without leaking API responses."""


@dataclass(frozen=True)
class CloudProfile:
    auth_url: str
    username: str
    project_name: str
    user_domain: str = "Default"
    project_domain: str = "Default"
    region_name: str = ""
    ca_file: str = ""
    interface: str = "public"

    def validate(self) -> None:
        try:
            parts = urlsplit(self.auth_url)
            valid_url = parts.scheme in ("http", "https") and parts.hostname and parts.port != 0
        except ValueError:
            valid_url = False
        if not valid_url:
            raise UserError(
                "올바른 OpenStack 인증 주소를 입력하세요. 예: https://cloud.example:5000/v3"
            )
        if parts.username or parts.password or parts.query or parts.fragment:
            raise UserError("인증 주소에는 계정 정보, 쿼리 문자열, 프래그먼트를 넣을 수 없습니다.")
        if not all(
            (
                self.username.strip(),
                self.project_name.strip(),
                self.user_domain.strip(),
                self.project_domain.strip(),
            )
        ):
            raise UserError("사용자, 프로젝트, 도메인을 모두 입력하세요.")
        if self.ca_file and not Path(self.ca_file).is_file():
            raise UserError("CA 인증서 파일이 없습니다. 올바른 인증서 파일을 선택하세요.")
        if self.interface not in ("public", "internal"):
            raise UserError("API 접속 경로는 public 또는 internal이어야 합니다.")

    @property
    def identity_url(self) -> str:
        parts = urlsplit(self.auth_url.strip())
        path = parts.path.rstrip("/")
        if not path:
            path = "/v3"
        return urlunsplit((parts.scheme, parts.netloc, path, "", ""))

    def scope_key(self, project_id: str) -> str:
        value = f"{self.identity_url}\n{project_id}\n{self.user_domain}\n{self.username}"
        return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class LoginSession:
    username: str
    project_name: str
    project_id: str
    scope_key: str


@dataclass(frozen=True)
class Desktop:
    id: str
    name: str
    status: str
    addresses: tuple[str, ...] = ()
    task_state: str | None = None

    def allows(self, action: str) -> bool:
        if self.task_state:
            return False
        if action == "start":
            return self.status == "SHUTOFF"
        if action in ("stop", "reboot", "connect"):
            return self.status == "ACTIVE"
        return False
