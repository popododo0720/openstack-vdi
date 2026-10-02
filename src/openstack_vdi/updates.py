from __future__ import annotations

import ctypes
import hashlib
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtWidgets import QMessageBox

from . import __version__
from .broker_client import BrokerBackend
from .models import UserError


def newer(version):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise UserError("업데이트 버전 형식이 올바르지 않습니다.")
    return tuple(map(int, version.split("."))) > tuple(map(int, __version__.split(".")))


def download_update(backend, release, directory=None):
    if not newer(release.get("version", "")):
        raise UserError("현재 버전보다 새로운 업데이트가 아닙니다.")
    url = release.get("url", "")
    origin, source = urlsplit(backend.url), urlsplit(url)
    if (
        source.scheme != "https"
        or source.netloc != origin.netloc
        or source.username
        or source.fragment
    ):
        raise UserError("업데이트는 설정된 VDI 서버의 HTTPS 주소에서만 받을 수 있습니다.")
    digest = release.get("sha256", "")
    if not re.fullmatch(r"[a-fA-F0-9]{64}", digest):
        raise UserError("업데이트 파일 검증 정보가 없습니다.")
    root = Path(tempfile.mkdtemp(prefix="OpenStackVDI-update-", dir=directory))
    path = root / "OpenStackVDI-Setup.exe"
    try:
        hasher = hashlib.sha256()
        size = 0
        with backend.http.get(
            url, stream=True, timeout=(5, 30), verify=backend.verify, allow_redirects=False
        ) as response:
            if response.status_code != 200:
                raise UserError("업데이트를 받지 못했습니다. 잠시 후 다시 시도하세요.")
            with path.open("xb") as output:
                for chunk in response.iter_content(1024 * 1024):
                    size += len(chunk)
                    if size > 300 * 1024 * 1024:
                        raise UserError("업데이트 파일이 허용 크기를 초과했습니다.")
                    hasher.update(chunk)
                    output.write(chunk)
        if hasher.hexdigest() != digest.lower():
            raise UserError("업데이트 파일 검증에 실패했습니다. 설치하지 않았습니다.")
        return path
    except Exception:
        path.unlink(missing_ok=True)
        root.rmdir()
        raise


def show_update_dialog(window):
    if not isinstance(window.backend, BrokerBackend) or window.session is None:
        QMessageBox.information(
            window,
            "앱 정보",
            f"OpenStack VDI {__version__}\n업데이트는 VDI 서버에 로그인한 뒤 확인하세요.",
        )
        return

    def checked(release):
        if not release or not newer(release.get("version", "")):
            QMessageBox.information(
                window, "앱 정보", f"OpenStack VDI {__version__}\n등록된 최신 버전입니다."
            )
            return
        if os.name != "nt":
            QMessageBox.information(
                window,
                "업데이트",
                f"새 버전 {release['version']}이 있습니다.\n"
                "Linux는 관리자가 배포한 패키지로 업데이트하세요.",
            )
            return
        if (
            QMessageBox.question(
                window,
                "앱 업데이트",
                f"{__version__} → {release['version']} 업데이트를 설치할까요?\n"
                "연결 창과 앱을 닫습니다. 업무용 PC는 계속 켜져 있습니다.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        def install(path):
            from ctypes import wintypes as w

            shell = ctypes.WinDLL("shell32", use_last_error=True)
            shell.ShellExecuteW.argtypes = [
                w.HWND,
                w.LPCWSTR,
                w.LPCWSTR,
                w.LPCWSTR,
                w.LPCWSTR,
                ctypes.c_int,
            ]
            shell.ShellExecuteW.restype = ctypes.c_void_p
            result = shell.ShellExecuteW(
                None, "runas", str(path), "/SILENT /NORESTART", str(path.parent), 1
            )
            if not result or result <= 32:
                raise UserError("업데이트 설치가 취소됐거나 설치 프로그램을 실행하지 못했습니다.")
            window.remote.close()
            window.close()

        window._run(
            lambda: download_update(window.backend, release), install, "업데이트 다운로드·검증 중…"
        )

    window._run(window.backend.release, checked, "업데이트 확인 중…")
