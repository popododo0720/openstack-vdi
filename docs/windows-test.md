# Windows 테스트 VM 준비

첫 테스트에는 Windows VM 한 대와 접속할 PC 한 대면 충분합니다.
폐쇄망과 업무망 두 개를 완전히 구성하는 단계는 이후에 진행합니다.

## qcow2를 받았을 때

1. 업로드가 끝난 정확한 파일 경로를 확인합니다. 업로드 중인 파일은 등록하지 않습니다.
2. `qemu-img info --output=json IMAGE.qcow2`로 형식, 가상 디스크 크기,
   backing file 유무를 확인합니다. 외부 backing file이 있으면 독립된 이미지로
   변환한 뒤 등록해야 합니다. 원본은 보존합니다.
3. 원본 Windows의 부팅 모드(BIOS/UEFI), VirtIO 디스크/네트워크 드라이버를 확인합니다.
   디스크 형식이 qcow2라는 이유만으로 UEFI나 VirtIO 지원이 보장되지는 않습니다.
4. Glance에 **private** 이미지로 등록합니다. Windows 이미지를 공개 저장소에 올리지 않습니다.
5. 테스트 프로젝트의 네트워크, security group, flavor를 명시해 VM 한 대를 생성합니다.
   시작 사양은 4 vCPU / RAM 8 GiB 정도로 잡되 루트 디스크는 qcow2의 가상 크기 이상으로
   맞춥니다. Windows 11 이미지는 원본이 요구하는 UEFI/TPM 구성을 함께 확인합니다.

## VM 안에서 준비할 것

관리자 PowerShell에서 [설치 스크립트](../scripts/setup-windows-rustdesk.ps1)를 실행하면
고정 버전/체크섬을 확인하고 RustDesk 서비스와 서버 설정을 적용할 수 있습니다.

```powershell
.\setup-windows-rustdesk.ps1 -IdServer 'SERVER_IP:21116' -RelayServer 'SERVER_IP:21117' -ServerKey 'SERVER_PUBLIC_KEY'
```

외부 다운로드가 제한되면 공식 RustDesk 1.4.9 설치 EXE를 미리 전달하고
`-InstallerPath 'C:\Setup\rustdesk-1.4.9-x86_64.exe'`를 추가합니다.
이 경우에도 고정 SHA-256 검사를 수행합니다. 설치 중 임시 설정 가져오기 서비스와
실제 실행 서비스를 구분하여 후자가 준비된 뒤 접속 설정을 적용합니다.

별도로 생성한 무인 접속 비밀번호는 `C:\ProgramData\OpenStackVDI\rustdesk-access.json`에
저장되며 SYSTEM/Administrators만 읽을 수 있습니다. 스크립트 출력에는 비밀번호를 넣지 않습니다.
이 파일을 공개 저장소나 일반 사용자 공유 폴더에 복사하지 않습니다.
Windows/OpenStack 비밀번호는 이 스크립트에 전달하지 않습니다.
기존 RustDesk가 설치돼 있으면 자동 업그레이드하지 않고 설정을 적용합니다.

- Windows가 정상 부팅되고 로그인할 수 있어야 합니다.
- RustDesk를 설치형 서비스로 설치합니다. 임시 실행만으로 구성하지 않습니다.
- 단말과 VM의 RustDesk에 같은 사내 ID/relay 서버 및 서버 공개키를 설정합니다.
- VM 전용의 무인 접속 비밀번호를 설정합니다. OpenStack 비밀번호를 재사용하지 않습니다.
- RustDesk에 표시된 ID를 런처의 `연결 ID 설정`에 등록합니다.
- 모니터 없는 VM에서도 화면이 나오는지 확인하고, 필요하면 가상 디스플레이를 구성합니다.
- 테스트에 필요하지 않은 파일 전송, 클립보드, 터널 기능은 사용 목적에 맞게 제한합니다.

처음에는 사용자가 RustDesk 접속 비밀번호와 Windows 로그인 정보를 직접 입력합니다.
OpenStack 로그인과 RustDesk/Windows 로그인을 자동으로 통합하는 기능은 아직 없습니다.

## OpenStack 접속 준비

앱에 필요한 값:

- Keystone 인증 주소 (`https://...:5000/v3`)
- 사용자, 비밀번호, 사용자 도메인
- 프로젝트 이름, 프로젝트 도메인
- 필요하면 리전과 public/internal endpoint 선택
- 자체 서명 인증서 환경의 신뢰할 수 있는 CA 인증서 파일

테스트용 일반 사용자와 전용 프로젝트를 권장합니다. Nova의 기본 VM 권한은
프로젝트 단위이므로 여러 사용자를 같은 프로젝트에 넣으면 서로의 VM에 대한
권한을 가질 수 있습니다. 앱은 현재 로그인한 프로젝트의 VM만 조회·조작하지만,
클라우드 관리자의 권한을 제한하는 보안 경계 역할을 하지는 않습니다.

`전원 정지`는 VM 정지이며 VM 삭제가 아닙니다. 종료 유예 시간 이후 강제 정지되는
동작은 Nova/하이퍼바이저 설정에 따릅니다. 작업을 저장한 뒤 실행합니다.
`재부팅`은 SOFT reboot를 요청하며 강제 재부팅으로 자동 전환하지 않습니다.

## 실제 검증 순서

1. 일반 사용자로 로그인하고 자신의 프로젝트 VM만 표시되는지 확인합니다.
2. 켜진 테스트 VM의 RustDesk ID를 등록하고 접속합니다.
3. 한글 입력, 해상도 변경, 다중 모니터, 로그온/UAC 화면을 확인합니다.
4. 원격 창을 닫고 다시 접속해 작업이 유지되는지 확인합니다.
5. 작업 저장 후 런처에서 재부팅하고 다시 연결합니다.
6. 전원 정지 → `꺼짐` 확인 → 켜기 → Windows/RustDesk 시작 후 재접속합니다.
7. 다른 프로젝트 사용자로 로그인해 VM과 RustDesk ID 매핑이 분리되는지 확인합니다.

VM의 `ACTIVE` 상태는 RustDesk가 접속 가능한 상태라는 뜻이 아닙니다.
런처의 `접속 창을 열었습니다` 또한 연결 성공 확인이 아닙니다. 현재 MVP는
RustDesk 세션 성공/종료를 수집하지 않고 별도 프로세스를 실행합니다.

## 운영 범위

이 MVP는 네이티브 접속과 VM 전원 관리 PoC입니다. RustDesk ID 등록은 편의 기능이며
접속 권한 부여가 아닙니다. RustDesk 측 인증/접근 통제는 별도로 적용해야 합니다.
런처 로그아웃은 이미 열린 RustDesk 세션을 종료하지 않습니다.
망별 세션 정책 강제, 중앙 SSO, 무단 단말 차단, 감사 로그, 기존 세션 권한 회수,
서로 다른 RustDesk 서버를 세션마다 선택하는 기능은 아직 구현하지 않았습니다.
따라서 현재 패키지 자체를 검증된 폐쇄망/망 분리 제품으로 취급하지 않습니다.

## 참고

- https://docs.openstack.org/nova/latest/configuration/policy.html
- https://docs.openstack.org/openstacksdk/latest/user/proxies/compute.html
- https://rustdesk.com/docs/en/client/
- https://rustdesk.com/docs/en/self-host/
- https://rustdesk.com/docs/en/self-host/client-configuration/advanced-settings/
