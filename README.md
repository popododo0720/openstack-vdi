# OpenStack VDI

OpenStack 계정으로 로그인하고 내 프로젝트의 VM을 켜거나 재부팅한 뒤
RustDesk로 접속하는 Windows/Linux용 네이티브 런처입니다.

실행 가능한 초기 MVP입니다. RustDesk는 별도로 설치합니다.
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

Windows에서는 `scripts/run-windows.ps1`도 사용할 수 있습니다.

## 구현된 기능

- 프로젝트 범위의 OpenStack 비밀번호 인증, CA 인증서 검증
- 프로젝트 VM 목록과 5초 간격 상태 갱신
- VM 켜기, 확인 대화상자가 있는 전원 정지 / SOFT 재부팅
- 사용자·클라우드·프로젝트·VM별 RustDesk ID 설정
- 설치된 RustDesk를 별도 프로세스로 실행 (`--connect ID`)
- 네트워크 요청의 백그라운드 처리, 데모 모드

비밀번호와 토큰은 파일에 저장하지 않습니다. 접속 주소, 사용자·프로젝트 이름,
인증서 경로, RustDesk 경로·ID만 OS별 사용자 설정 폴더에 저장합니다.
VM 이름으로 필터링해 권한을 판단하지 않고, API 작업 전에 프로젝트 소유권을 확인합니다.

## 테스트 VM

[Windows 테스트 절차](docs/windows-test.md)를 참고하세요.
먼저 Windows VM 한 대에 RustDesk를 설치한 뒤 연결 ID를 등록하면 됩니다.
자동 VM 생성, 통합 SSO, 중앙 RustDesk 접근 제어는 아직 포함하지 않습니다.

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
RustDesk는 패키지에 포함하지 않습니다.

## 라이선스

AGPL-3.0-only. RustDesk는 별도 프로젝트이며 본 저장소에 포함하지 않습니다.
의존성 고지는 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)를 참고하세요.
