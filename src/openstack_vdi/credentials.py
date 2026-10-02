"""Opt-in Windows Credential Manager storage; never falls back to plaintext."""

from __future__ import annotations

import ctypes
import hashlib
import os
from ctypes import wintypes as w

from .models import CloudProfile, UserError


class Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", w.DWORD),
        ("Type", w.DWORD),
        ("TargetName", w.LPWSTR),
        ("Comment", w.LPWSTR),
        ("LastWritten", w.FILETIME),
        ("CredentialBlobSize", w.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
        ("Persist", w.DWORD),
        ("AttributeCount", w.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", w.LPWSTR),
        ("UserName", w.LPWSTR),
    ]


def target(profile: CloudProfile):
    value = (
        f"{profile.identity_url}\n{profile.username}\n{profile.user_domain}\n{profile.project_name}"
    )
    return "OpenStackVDI/" + hashlib.sha256(value.encode()).hexdigest()


def api():
    if os.name != "nt":
        raise UserError("로그인 정보 저장은 Windows 자격 증명 관리자에서만 지원합니다.")
    dll = ctypes.WinDLL("advapi32", use_last_error=True)
    dll.CredWriteW.argtypes = [ctypes.POINTER(Credential), w.DWORD]
    dll.CredReadW.argtypes = [
        w.LPCWSTR,
        w.DWORD,
        w.DWORD,
        ctypes.POINTER(ctypes.POINTER(Credential)),
    ]
    dll.CredDeleteW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD]
    dll.CredFree.argtypes = [ctypes.c_void_p]
    return dll


def save(profile, password):
    raw = password.encode("utf-16-le")
    if len(raw) > 2560:
        raise UserError("자격 증명 관리자에 저장하기에는 비밀번호가 너무 깁니다.")
    blob = (ctypes.c_byte * len(raw)).from_buffer_copy(raw)
    credential = Credential(
        Type=1,
        TargetName=target(profile),
        CredentialBlobSize=len(raw),
        CredentialBlob=blob,
        Persist=2,
        UserName=profile.username,
    )
    if not api().CredWriteW(ctypes.byref(credential), 0):
        raise UserError("Windows 자격 증명 관리자에 로그인 정보를 저장하지 못했습니다.")


def read(profile):
    if os.name != "nt":
        return ""
    dll = api()
    result = ctypes.POINTER(Credential)()
    if not dll.CredReadW(target(profile), 1, 0, ctypes.byref(result)):
        return ""
    try:
        return ctypes.string_at(
            result.contents.CredentialBlob, result.contents.CredentialBlobSize
        ).decode("utf-16-le")
    finally:
        dll.CredFree(result)


def forget(profile):
    if os.name == "nt":
        api().CredDeleteW(target(profile), 1, 0)
