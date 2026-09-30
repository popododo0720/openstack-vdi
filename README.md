# OpenStack VDI

OpenStack 계정으로 로그인하고 내 프로젝트의 VM을 켜거나 재부팅한 뒤
RustDesk로 접속하는 Windows/Linux용 네이티브 런처입니다.

현재 개발 중인 MVP입니다. RustDesk는 별도로 설치합니다.
RustDesk의 인증과 Windows 로그인을 OpenStack 인증으로 대체하지 않습니다.

## 실행

Python 3.11 이상과 [uv](https://docs.astral.sh/uv/)가 필요합니다.

```sh
uv sync
uv run openstack-vdi
```

클라우드 없이 UI와 전원 동작을 살펴보려면:

```sh
uv run openstack-vdi --demo
```

## 라이선스

AGPL-3.0-only. RustDesk는 별도 프로젝트이며 본 저장소에 포함하지 않습니다.

