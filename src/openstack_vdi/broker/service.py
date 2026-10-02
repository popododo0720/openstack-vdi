from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from keystoneauth1 import session as ks_session
from keystoneauth1.identity import v3
from pydantic import BaseModel, Field, SecretStr

from openstack_vdi.backend import OpenStackBackend, safe_error
from openstack_vdi.models import CloudProfile

log = logging.getLogger("vdi.audit")


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: SecretStr


class Heartbeat(BaseModel):
    boot_id: str = Field(min_length=1, max_length=128)
    ready: bool


class Power(BaseModel):
    action: Literal["start", "stop", "reboot"]


def authenticate(config, username, password):
    """Unscoped Keystone login: end users do not need any Nova project role."""
    auth = v3.Password(
        auth_url=config["identity_url"],
        username=username,
        password=password,
        user_domain_name=config.get("user_domain", "Default"),
        unscoped=True,
    )
    session = ks_session.Session(auth=auth, verify=config["ca_file"], timeout=15)
    try:
        return auth.get_access(session).user_id
    finally:
        session.session.close()


def service_backend(config):
    backend = OpenStackBackend()
    service = config["service"]
    backend.login(CloudProfile(**service["profile"]), service["password"])
    return backend


class State:
    def __init__(self, path: Path, clock=time.monotonic):
        self.path, self.clock = path, clock
        self.lock = threading.RLock()
        self.sessions = {}
        self.beats = {}
        self.pending = {}
        self.attempts = {}

    def config(self):
        # Administrative changes (including revocations) take effect on the next request.
        return json.loads(self.path.read_text(encoding="utf-8"))

    def identity(self, authorization: str):
        token = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
        key = hashlib.sha256(token.encode()).hexdigest()
        with self.lock:
            entry = self.sessions.get(key)
            if not entry or entry[1] <= self.clock():
                self.sessions.pop(key, None)
                raise HTTPException(401, "로그인이 만료됐습니다. 다시 로그인하세요.")
        config = self.config()
        if entry[0] not in config["assignments"]:
            raise HTTPException(403, "데스크톱 사용 권한이 없습니다.")
        return entry[0], config

    def assigned(self, identity, vm):
        user, config = identity
        if vm not in config["assignments"].get(user, []) or vm not in config["desktops"]:
            raise HTTPException(403, "이 데스크톱에 대한 권한이 없습니다.")
        return config["desktops"][vm]

    def readiness(self, vm):
        with self.lock:
            beat = self.beats.get(vm)
            if not beat or self.clock() - beat["time"] > 25:
                return False, "", "Windows 응답 대기 중"
            pending = self.pending.get(vm)
            if pending:
                # A fresh heartbeat alone is NOT evidence of a completed reboot.
                if pending["action"] == "stop" or beat["boot_id"] == pending["boot_id"]:
                    return False, beat["boot_id"], "Windows 재시작 대기 중"
                if beat["time"] <= pending["time"]:
                    return False, beat["boot_id"], "Windows 재시작 대기 중"
                del self.pending[vm]
            return (
                beat["ready"],
                beat["boot_id"],
                ("접속 준비됨" if beat["ready"] else "원격 접속 서비스 준비 중"),
            )


def create_app(
    config_path=None, auth_fn=authenticate, backend_factory=service_backend, clock=time.monotonic
):
    state = State(Path(config_path or os.environ["VDI_BROKER_CONFIG"]), clock)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.vdi = state

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # Pydantic's default response can echo password/token input.
        return JSONResponse({"detail": "요청 형식이 올바르지 않습니다."}, status_code=422)

    @app.exception_handler(Exception)
    async def request_failed(request, exc):
        return JSONResponse({"detail": safe_error(exc)}, status_code=503)

    def identity(authorization: Annotated[str, Header()] = ""):
        return state.identity(authorization)

    authorized = Depends(identity)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/login")
    def login(body: Login, request: Request):
        now = clock()
        address = request.client.host if request.client else "unknown"
        with state.lock:
            state.attempts = {k: v for k, v in state.attempts.items() if now - v[0] < 60}
            for key in ("user:" + body.username.casefold(), "ip:" + address):
                start, count = state.attempts.get(key, (now, 0))
                if count >= 20:
                    raise HTTPException(429, "로그인 시도가 많습니다. 1분 뒤 다시 시도하세요.")
                state.attempts[key] = start, count + 1
        config = state.config()
        try:
            user = auth_fn(config, body.username, body.password.get_secret_value())
        except Exception as error:
            log.info("login denied")
            raise HTTPException(401, "계정과 비밀번호를 확인하세요.") from error
        if user not in config["assignments"]:
            raise HTTPException(403, "배정된 데스크톱이 없습니다. 관리자에게 문의하세요.")
        token = secrets.token_urlsafe(32)
        with state.lock:
            state.sessions = {k: v for k, v in state.sessions.items() if v[1] > now}
            if len(state.sessions) >= 10000:
                raise HTTPException(503, "잠시 후 다시 로그인하세요.")
            state.sessions[hashlib.sha256(token.encode()).hexdigest()] = (user, now + 8 * 3600)
        log.info("login user=%s", user)
        return {"token": token, "user_id": user, "username": body.username}

    @app.post("/logout")
    def logout(authorization: Annotated[str, Header()] = ""):
        with state.lock:
            state.sessions.pop(
                hashlib.sha256(authorization.removeprefix("Bearer ").encode()).hexdigest(), None
            )
        return {"ok": True}

    @app.get("/desktops")
    def desktops(user=authorized):
        _, config = user
        backend = backend_factory(config)
        try:
            # Cloud project filtering is an additional boundary, not the assignment rule.
            allowed = set(config["assignments"][user[0]])
            rows = []
            for desktop in backend.list_desktops():
                if desktop.id not in allowed:
                    continue
                assigned = state.assigned(user, desktop.id)
                ready, boot, message = state.readiness(desktop.id)
                row = asdict(desktop)
                row.update(
                    name=assigned["name"],
                    addresses=[],
                    peer_id=assigned["peer_id"],
                    ready=bool(ready and desktop.status == "ACTIVE" and not desktop.task_state),
                    boot_id=boot,
                    readiness_message=message,
                )
                rows.append(row)
            return rows
        finally:
            backend.close()

    @app.post("/desktops/{vm}/power")
    def power(vm: str, body: Power, user=authorized):
        state.assigned(user, vm)
        # Serialize only power operations. Never duplicate a request while Nova catches up.
        with state.lock:
            previous = state.pending.get(vm)
            if previous and previous["action"] == body.action and clock() - previous["time"] < 60:
                raise HTTPException(409, "이미 전원 작업이 진행 중입니다.")
            backend = backend_factory(user[1])
            try:
                backend.power(vm, body.action)
                state.pending[vm] = {
                    "action": body.action,
                    "time": clock(),
                    "boot_id": state.beats.get(vm, {}).get("boot_id", ""),
                }
            finally:
                backend.close()
        log.info("power user=%s vm=%s action=%s", user[0], vm, body.action)
        return {"ok": True}

    @app.post("/desktops/{vm}/connect")
    def connect(vm: str, user=authorized):
        assignment = state.assigned(user, vm)
        if not state.readiness(vm)[0]:
            raise HTTPException(409, "Windows의 접속 준비를 기다리고 있습니다.")
        # No remote passwords in broker responses. RustDesk performs remote authentication.
        return {"peer_id": assignment["peer_id"]}

    @app.post("/agent/{vm}/heartbeat")
    def heartbeat(vm: str, body: Heartbeat, authorization: Annotated[str, Header()] = ""):
        config = state.config()
        expected = config["desktops"].get(vm, {}).get("agent_token", "")
        token = authorization.removeprefix("Bearer ")
        if not expected or not hmac.compare_digest(token, expected):
            raise HTTPException(403, "인증 실패")
        with state.lock:
            state.beats[vm] = {"time": clock(), **body.model_dump()}
        return {"ok": True}

    @app.get("/client-release")
    def release(user=authorized):
        return user[1].get("client_release", {})

    @app.get("/download/client")
    def client_download(user=authorized):
        filename = user[1].get("client_installer", "")
        if not filename or not Path(filename).is_file():
            raise HTTPException(404, "설치 파일이 등록되지 않았습니다.")
        return FileResponse(filename, filename="OpenStackVDI-Setup.exe")

    return app
