# 검증 기록 (2026-10-01)

초기 MVP를 실제 OpenStack 테스트 클러스터에서 검증했습니다.

- 단위/Qt 테스트: 37개 통과.
- Linux PyInstaller 패키지 생성 및 offscreen 데모 실행 확인.
- GitHub Actions에서 Linux/Windows 테스트 통과, Windows 실행 패키지 생성 성공.
  커밋 `c3a0b21`의 빌드에서 패키징한 실행 파일 자체의 SDK 초기화 검사도 통과했습니다.
- 앱의 OpenStackBackend로 실제 인증과 프로젝트 범위 VM 목록 조회 성공.
- Terraform으로 Ubuntu 24.04 VM, Cinder 부팅 볼륨, 전용 네트워크와 floating IP 생성.
- 최종 cloud-init 설정만으로 Docker와 RustDesk hbbs/hbbr 자동 설치 성공.
- 앱의 전원 제어 코드로 해당 VM에 SOFT 재부팅 요청 성공.
- 부팅 ID 변경, systemd 서비스 자동 복구, 두 컨테이너 running 확인.
- 재부팅 전후 서버 공개키 SHA-256 일치.
- 외부에서 TCP 21115/21116/21117 연결 성공, VM 내부 UDP 21116 리스너 확인.
- 최종 Terraform plan: 변경 없음.
- Windows 11 qcow2 무결성 검사, 체크섬 검증 업로드, Glance private/active 확인.
- 4 vCPU / 8 GiB / 80 GiB Windows VM 생성 및 Windows 초기 설정 화면 부팅 확인.
- Windows 게스트 에이전트와 내부 IPv4 통신 확인.
- Windows RustDesk 서비스 설치, 사내 ID/릴레이 서버 설정, 서버 DB의 peer 등록 확인.
- Windows 최초 설정 완료 및 테스트 계정의 바탕화면 진입 확인.
- 생성한 로컬 테스트 계정의 Windows 인증 성공 확인.
- Windows 초기 설정 중 재부팅 후 RustDesk 서비스 자동 실행과 동일 ID 유지 확인.

- Linux 네이티브 런처의 실제 로그인·VM 선택·접속 버튼에서 RustDesk 실행 확인.
  Qt 테스트 하네스로 화면 컨트롤을 조작했으며 실제 OpenStack/RustDesk를 사용했습니다.
- RustDesk 클라이언트에서 Windows 잠금 화면과 `vdi` 로그인 후 바탕화면 수신 확인.
- 원격 마우스로 메모장과 저장 창을 조작하고 키보드로 테스트 문구 입력·저장 성공.
  게스트 에이전트로 저장 파일을 별도 읽어 `OpenStack VDI E2E 2026-10-01` 일치 확인.
- 설치 스크립트 재실행: 영구 암호 설정 응답과 인증 방식 확인, 서비스 재시작 후 연결 복구.
- 앱의 OpenStackBackend로 Windows VM 정지(`SHUTOFF`) → 시작(`ACTIVE`) 완료.
  부팅 후 서비스 자동 실행, 저장 파일 유지, 기존 RustDesk 암호로 화면 재접속 확인.
- 부팅 직후 `ACTIVE`여도 RustDesk는 일시적으로 offline이었습니다. Windows 서비스 시작 후 재시도했습니다.

최초 암호 입력에서 인증 거부가 있었고, 암호 재적용과 입력 포커스 확보 후 성공했습니다.
최초 실패의 정확한 원인은 확정하지 않았습니다. 설치 스크립트는 성공 응답을 검사하도록 보강했습니다.

## Windows 접속 단말 실연결

- Terraform으로 별도 `windows-11-vdi-client-poc` VM을 생성하고 초기 설정을 완료했습니다.
- Windows 단말에 배포용 EXE, CA, 연결 설정, 바탕화면 바로가기를 설치했습니다.
- 실제 EXE에서 OpenStack 로그인 → 업무용 VM 선택 → 접속 버튼 → RustDesk 인증 →
  업무용 Windows 바탕화면 수신을 확인했습니다.
- 로그인 계정 `vdi-prototype`은 테스트 프로젝트의 `member` 역할만 사용합니다.
  프로젝트 이름은 `admin`이지만 계정에 관리자 역할을 부여하지 않았습니다.
- 원격 키보드·마우스로 메모장 문서를 작성해 업무용 VM의 바탕화면에
  `client-prototype.txt`를 저장했습니다. 게스트 에이전트로 별도 읽어
  `windows client to vdi prototype 2026-10-01` 내용과 일치함을 확인했습니다.
- Windows 앱의 전원 정지 버튼으로 `SHUTOFF`, 켜기 버튼으로 `ACTIVE` 전환을 확인했습니다.
  상태 확인용 API 호출은 읽기 전용이며 전원 조작은 실제 Windows GUI에서 수행했습니다.
- 부팅 후 RustDesk 자동 실행, 기존 암호로 재접속, Windows 로그인과 저장 파일 유지 확인.
- 접속용 Windows 재부팅 후에도 RustDesk 서비스와 ID, 런처 설정이 유지됐습니다.
- 최종 Terraform plan 종료 코드 0: 변경 없음. 임시 설치 파일 전송 서버는 종료했습니다.

실제 Windows 패키지에서 발견한 SDK 캐시 백엔드 누락을 hidden import로 수정했고,
Linux/Windows 빌드에서 완성된 실행 파일에 `--check-package` 검사를 추가했습니다.
검증한 Windows 빌드는 GitHub Actions 실행 `36810736986`, 소스 커밋 `c3a0b21`입니다.

현재는 같은 테스트 프로젝트의 VM 13대가 목록에 표시됩니다. 사용자별 전용 VM만
노출하는 운영용 접근 정책은 아직 적용하지 않았습니다.

아직 검증하지 않은 항목: 한글 IME·다중 모니터·UAC,
일반 사용자별 접근 정책 및 업무망/폐쇄망 분리.
포트 응답과 서버 정상 실행만으로 화면 전송 성공을 판정하지 않습니다.

로컬 상세 로그는 Git에서 제외한 `artifacts/`에 보관합니다.
이번 실연결 증거는 `artifacts/rustdesk-e2e/`의 `input-verified.png`,
`launcher-live.png`, `powercycle-reconnected.png`, `powercycle.log`에 보관합니다.
OpenStack 인증 정보, Terraform state 및 운영 tfvars는 저장소에 포함하지 않습니다.

Windows 단말 증거는 `artifacts/client-e2e/`의 `launcher-authenticated.png`,
`remote-input-saved.png`, `powercycle-reconnected.png`, `power-stop.log`,
`power-start.log`, `final-terraform-plan.log`에 보관합니다.
