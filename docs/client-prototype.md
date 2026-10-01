# Windows 단말 프로토타입

세 VM의 역할은 다음과 같습니다.

| VM | 역할 |
| --- | --- |
| `windows-11-vdi-client-poc` | 사용자가 앉아 있는 접속용 Windows. 런처와 RustDesk 실행 |
| `vdi-server-poc` | Ubuntu의 RustDesk ID/릴레이 서버 |
| `windows-11-vdi-poc` | 원격으로 접속해서 일하는 업무용 Windows |

OpenStack 콘솔에서 **접속용 VM**을 열고 바탕화면의 `OpenStack VDI`를 실행합니다.
OpenStack 계정으로 로그인하고 업무용 VM을 선택한 다음 `데스크톱 접속`을 누릅니다.
RustDesk 암호를 입력하면 업무용 Windows 화면이 별도 창으로 열립니다.
Windows가 잠겨 있으면 업무용 Windows 계정으로 로그인합니다.
세 인증(OpenStack, RustDesk, Windows)은 현재 별개입니다.

## 배포

1. [인프라 설정](../infra/README.md)의 `enable_windows_client = true`로 접속용 VM을 생성합니다.
2. Windows 최초 설정을 완료하고 단말 사용자를 만듭니다.
3. 단말에도 RustDesk를 설치하고 ID 서버·릴레이·공개키를 설정합니다.
4. GitHub Actions의 `OpenStackVDI-Windows` 아티팩트 전체를 ZIP으로 준비합니다.
   루트에 `OpenStackVDI.exe`와 `_internal`이 있어야 합니다.
5. 관리자 PowerShell에서 `scripts/setup-windows-client.ps1`을 실행합니다.

설치 스크립트는 ZIP의 SHA-256을 검사하고 Program Files에 압축을 풀며,
바탕화면 바로가기와 사용자별 연결 설정을 만듭니다. 비밀번호는 저장하지 않습니다.
다른 사용자의 설정을 준비할 경우 `-ProfileDirectory`에 해당 사용자의
`AppData\Local\OpenStackVDI` 경로를 명시합니다. 기존 설정은 덮어쓰지 않습니다.

필수 인자는 `PackagePath`, `PackageSha256`, `CaPath`, `AuthUrl`, `Username`,
`ProjectName`, `ProjectId`, `DesktopId`, `PeerId`입니다. `ProjectId`는 OpenStack
프로젝트 UUID, `DesktopId`는 업무용 VM UUID입니다. 서버 CA는 신뢰할 수 있는
관리 경로로 받은 인증서를 사용합니다.

## 검증한 사용자 흐름

- 접속용 Windows에서 배포용 EXE 실행 → 실제 OpenStack 로그인 → 업무용 VM 목록 표시
- `데스크톱 접속` → RustDesk 인증 → 업무용 Windows 화면
- 원격 화면에서 키보드·마우스로 문서 작성 및 저장
- 원격 창을 닫고 런처로 돌아와 다시 접속
- 작업 저장 후 런처에서 업무용 VM 전원 정지 → 꺼짐 확인 → 켜기 → 부팅 후 재접속

같은 테스트 프로젝트에 세 VM이 있으면 모두 목록에 표시됩니다. 전원 작업은
업무용 VM에 수행합니다. 운영 환경의 사용자별 프로젝트·접근 정책과 망 분리는
별도 설계 대상이며 이 단일망 프로토타입의 완료 조건과 구분합니다.

2026-10-01 위 흐름을 실제 Windows 배포 패키지와 OpenStack에서 확인했습니다.
[검증 기록](validation.md)에 빌드와 실연결 범위를 정리했습니다.
현재 접속용 VM의 Windows 계정은 `client`, 앱 계정은 `vdi-prototype`,
업무용 Windows 계정은 `vdi`입니다. 각 암호는 별도로 전달하며 저장소에 포함하지 않습니다.
