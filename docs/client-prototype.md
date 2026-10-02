# Windows 단말 프로토타입

| VM | 역할 |
| --- | --- |
| `windows-11-vdi-client-poc` | 사용자가 앉아 있는 접속용 Windows. 앱과 RustDesk 실행 |
| `vdi-server-poc` | Ubuntu의 배정·전원 브로커와 RustDesk ID/릴레이 서버 |
| `windows-11-vdi-poc` | 원격으로 접속해서 일하는 업무용 Windows |

OpenStack 콘솔에서 **접속용 VM**을 열고 `client` 계정으로 로그인합니다.
바탕화면 **OpenStack VDI**에서 `vdi-prototype` 계정으로 로그인하면 배정된
**업무용 PC** 한 대가 표시됩니다. 암호는 별도 전달하며 저장소에 포함하지 않습니다.

- **데스크톱 접속 / 켜고 접속**: 꺼진 PC는 자동으로 켜고 준비를 기다린 뒤 연결합니다.
- **재부팅 후 접속**: Windows가 새로 부팅됐음을 확인하고 원격 창을 다시 엽니다.
- **접속 취소**: 기다리던 자동 접속만 취소합니다. 전원 작업은 유지됩니다.
- **연결 창 닫기**: PC와 프로그램은 계속 실행됩니다.
- **PC 종료**: 저장하지 않은 작업이 사라질 수 있어 확인을 받습니다.
- **로그아웃**: 이 앱이 연 원격 창을 닫고 저장한 앱 로그인 정보도 삭제합니다.

RustDesk 첫 연결에서 암호를 입력하고 ‘비밀번호 기억’을 선택할 수 있습니다.
Windows 잠금 화면은 업무용 계정 `vdi`로 해제합니다. 통합 SSO는 아닙니다.

0.2의 [관리형 배포·배정 설정](managed-desktops.md)을 참고하세요.
Windows 설치 EXE는 GitHub Actions의 `OpenStackVDI-Installer` 아티팩트에 있습니다.
브로커 주소·CA·RustDesk 서버 설정은 관리자가 설치 시 배포합니다.

이전 `scripts/setup-windows-client.ps1`은 OpenStack 프로젝트에 직접 로그인하는
기존 모드용입니다. 관리형 모드에는 enrollment를 받는 새 설치 프로그램을 사용합니다.
프로토타입의 [검증 기록](validation.md)과 운영 범위를 함께 확인하세요.
