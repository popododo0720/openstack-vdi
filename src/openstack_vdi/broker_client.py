from __future__ import annotations

import requests

from .models import CloudProfile, Desktop, LoginSession, UserError


class BrokerBackend:
    def __init__(self):
        self.session = None
        self.http = requests.Session()
        self.url = ""
        self.verify = True

    def request(self, method, path, **kwargs):
        response = self.http.request(
            method,
            self.url + path,
            timeout=(5, 30),
            verify=self.verify,
            allow_redirects=False,
            **kwargs,
        )
        if response.status_code == 401:
            raise UserError("로그인이 만료됐거나 계정 정보가 틀렸습니다. 다시 로그인하세요.")
        if response.status_code == 403:
            raise UserError("이 데스크톱에 대한 권한이 없습니다. 관리자에게 배정을 확인하세요.")
        if response.status_code == 409:
            raise UserError(
                "데스크톱이 준비 중이거나 다른 작업을 처리 중입니다. 잠시 후 시도하세요."
            )
        if response.status_code == 429:
            raise UserError("로그인 시도가 많습니다. 1분 뒤 다시 시도하세요.")
        if not 200 <= response.status_code < 300:
            raise UserError("VDI 서버에 연결하지 못했습니다. 네트워크를 확인하고 다시 시도하세요.")
        return response.json()

    def login(self, profile: CloudProfile, password: str):
        profile.validate()
        self.url, self.verify = profile.broker_url.rstrip("/"), profile.ca_file or True
        data = self.request(
            "POST", "/login", json={"username": profile.username, "password": password}
        )
        self.http.headers["Authorization"] = "Bearer " + data["token"]
        self.session = LoginSession(
            profile.username, "내 데스크톱", data["user_id"], profile.scope_key(data["user_id"])
        )
        return self.session

    def list_desktops(self):
        return [
            Desktop(**(row | {"addresses": tuple(row.get("addresses", []))}))
            for row in self.request("GET", "/desktops")
        ]

    def power(self, server_id, action):
        self.request("POST", f"/desktops/{server_id}/power", json={"action": action})

    def connection_peer(self, server_id):
        return self.request("POST", f"/desktops/{server_id}/connect")["peer_id"]

    def release(self):
        return self.request("GET", "/client-release")

    def close(self):
        try:
            if self.session:
                self.request("POST", "/logout")
        except (requests.RequestException, UserError):
            pass  # Local logout must succeed even after expiry or network loss.
        finally:
            self.session = None
            self.http.headers.pop("Authorization", None)
            self.http.close()
