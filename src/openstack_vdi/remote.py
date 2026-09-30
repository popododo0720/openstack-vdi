from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from .models import UserError


def validate_peer_id(value: str) -> str:
    peer_id = value.strip().replace(" ", "")
    # Only IDs for the client's configured server. Never accept flags, URIs or passwords.
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{2,63}", peer_id):
        raise UserError("RustDesk ID를 입력하세요. 영문, 숫자, 밑줄, 하이픈만 사용할 수 있습니다.")
    return peer_id


def find_rustdesk(configured: str = "") -> str:
    if configured:
        path = Path(configured).expanduser()
        if not path.is_file():
            raise UserError("RustDesk 실행 파일을 찾지 못했습니다. 실행 파일 경로를 확인하세요.")
        if os.name != "nt" and not os.access(path, os.X_OK):
            raise UserError("선택한 RustDesk 파일에 실행 권한이 없습니다.")
        return str(path.resolve())
    found = shutil.which("rustdesk")
    if found:
        return found
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if base:
                candidate = Path(base) / "RustDesk" / "rustdesk.exe"
                if candidate.is_file():
                    return str(candidate)
    raise UserError("RustDesk를 설치하거나 설정에서 실행 파일을 선택하세요.")


def launch_rustdesk(peer_id: str, configured: str = "") -> None:
    executable = find_rustdesk(configured)
    args = [executable, "--connect", validate_peer_id(peer_id)]
    kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "shell": False,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen(args, **kwargs)
    except OSError as error:
        raise UserError(
            "RustDesk를 실행하지 못했습니다. 설치 상태와 실행 권한을 확인하세요."
        ) from error
