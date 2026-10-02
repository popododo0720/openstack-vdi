# OpenStack VDI

OpenStack 위의 업무용 Windows를 네이티브 앱에서 켜고 접속하는 VDI 프로토타입입니다.
사용자는 계정으로 로그인하고 배정된 PC를 선택합니다. RustDesk가 화면을 전송합니다.

0.2에서는 서버의 사용자별 배정 검사, Windows 준비 신호, 재부팅 후 자동 접속,
꺼진 PC 원클릭 접속, 접속 취소, Windows 설치·업데이트를 지원합니다.
[설정과 사용자 흐름](docs/managed-desktops.md)을 참고하세요.

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

Windows에서는 `scripts/run-windows.ps1`도 사용할 수 있습니다.

## 구현된 기능

- 브로커의 Keystone 사용자 인증, 사용자 UUID별 VM 배정과 API 권한 검사
- 배정된 PC만 표시하는 화면, 백그라운드 조회 중에도 유지되는 전원·접속 버튼
- 꺼진 PC 켜기 → 준비 대기 → 접속, 새 부팅 확인 후 재접속, 취소·시간 초과
- Windows의 실제 RustDesk 창 재사용과 연결 상태 관찰
- 선택적인 Windows 자격 증명 저장, 로그아웃·연결 종료·PC 종료 구분
- 회사 연결 설정을 적용하는 Windows 설치 프로그램과 검증된 업데이트 다운로드
- 기존 OpenStack 프로젝트 직접 연결 모드와 클라우드 없는 데모 모드

관리형 모드의 사용자에게는 Nova 프로젝트 역할이 필요하지 않습니다.
브로커 서비스 계정에만 필요한 프로젝트 역할을 부여합니다.
RustDesk 인증과 Windows 로그인을 통합 SSO로 대체하지는 않습니다.

## 테스트 VM

[서버 배포 절차](infra/README.md)로 OpenStack 안에 Ubuntu 서버 VM과
RustDesk ID/릴레이 서버를 먼저 만듭니다. 작업 PC에 서버를 설치하지 않습니다.

[Windows 테스트 절차](docs/windows-test.md)를 참고하세요.
업무용 Windows에는 RustDesk를 설치하고, 접속용 단말에는 이 런처와 RustDesk를 설치합니다.
접속용 단말도 VM으로 구성하는 절차는 [Windows 단말 프로토타입](docs/client-prototype.md)에 있습니다.
런처 내 자동 VM 생성, 통합 SSO, RustDesk 세션의 중앙 강제 회수는 아직 포함하지 않습니다.

## 개발 및 검증

```sh
uv sync --group dev
uv run ruff check src tests scripts
uv run pytest -q
```

GUI 테스트는 실제 Qt 위젯을 offscreen으로 실행합니다. 데모 테스트와 SDK mock 테스트는
실제 OpenStack/Windows/RustDesk 연결 성공을 의미하지 않습니다.

## 실행 패키지 만들기

```sh
uv run --group build python scripts/build.py
```

해당 운영체제에서 빌드합니다. Windows에서는 `dist/OpenStackVDI/OpenStackVDI.exe`가
생성됩니다. `_internal`을 포함한 **OpenStackVDI 폴더 전체**를 배포해야 합니다.
GitHub Actions에는 Linux/Windows 테스트와 Windows 패키지 생성 작업이 들어 있습니다.
RustDesk는 패키지에 포함하지 않습니다. Windows 설치 프로그램은 필요한 경우 공식 설치 파일을 받아 검증합니다.
설치 EXE는 GitHub Actions의 `OpenStackVDI-Installer` 아티팩트에 있습니다.

## 라이선스

AGPL-3.0-only. RustDesk는 별도 프로젝트이며 본 저장소에 포함하지 않습니다.
의존성 고지는 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)를 참고하세요.
