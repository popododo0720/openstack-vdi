# 검증 기록 (2026-09-30)

초기 MVP를 실제 OpenStack 테스트 클러스터에서 검증했습니다.

- 단위/Qt 테스트: 36개 통과.
- Linux PyInstaller 패키지 생성 및 offscreen 데모 실행 확인.
- 앱의 OpenStackBackend로 실제 인증과 프로젝트 범위 VM 목록 조회 성공.
- Terraform으로 Ubuntu 24.04 VM, Cinder 부팅 볼륨, 전용 네트워크와 floating IP 생성.
- 최종 cloud-init 설정만으로 Docker와 RustDesk hbbs/hbbr 자동 설치 성공.
- 앱의 전원 제어 코드로 해당 VM에 SOFT 재부팅 요청 성공.
- 부팅 ID 변경, systemd 서비스 자동 복구, 두 컨테이너 running 확인.
- 재부팅 전후 서버 공개키 SHA-256 일치.
- 외부에서 TCP 21115/21116/21117 연결 성공, VM 내부 UDP 21116 리스너 확인.
- 최종 Terraform plan: 변경 없음.

아직 검증하지 않은 항목: Windows 패키지 실행, Windows VM 전원 정지/시작,
실제 RustDesk 화면·키보드·마우스 연결, 사용자별 접근 정책 및 업무망/폐쇄망 분리.
포트 응답과 서버 정상 실행만으로 화면 전송 성공을 판정하지 않습니다.

로컬 상세 로그는 Git에서 제외한 `artifacts/`에 보관합니다.
OpenStack 인증 정보, Terraform state 및 운영 tfvars는 저장소에 포함하지 않습니다.
