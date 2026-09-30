# OpenStack 안에 VDI 서버 배포

Terraform으로 Ubuntu VM과 전용 네트워크를 만들고, cloud-init으로 VM 안에
RustDesk ID 서버(hbbs)와 relay(hbbr)를 설치합니다. 작업 PC에서는 Terraform만 실행합니다.
RustDesk 컨테이너를 작업 PC에 올리지 않습니다.

생성 리소스: 네트워크, 서브넷, 라우터, 제한된 security group, 포트, floating IP,
SSH 공개키, Cinder 부팅 디스크와 Ubuntu VM 한 대.
기존 OpenStack 클러스터 설정과 기존 VM은 변경하지 않습니다.

## 준비

1. 현재 테스트 프로젝트의 openrc와 신뢰할 수 있는 CA 인증서를 준비합니다.
2. Ubuntu 24.04 cloud image와 2 vCPU / RAM 2-4 GiB 이상의 flavor를 고릅니다.
3. `openstack/terraform.tfvars.example`을 `terraform.tfvars`로 복사해 실제 값으로 채웁니다.
   비밀번호는 tfvars에 쓰지 않습니다. 필요하면 사내 DNS 주소도 지정합니다.

```sh
source /path/to/current-openrc.sh
export OS_CACERT=/path/to/trusted-ca.crt
cd infra/openstack
terraform init
terraform plan -out=server.tfplan
terraform apply server.tfplan
terraform output
```

`terraform.tfstate`에는 운영 정보가 있으므로 Git에 넣지 않습니다.
나중에 업로드한 Windows qcow2로 VM을 만들 때 `desktop_network_id` 출력의 네트워크를
사용하면 이 테스트 서버와 같은 내부망에서 연결할 수 있습니다.

## 서버 확인

출력된 floating IP로 접속합니다. 최초 부팅 시 Docker 설치와 이미지 다운로드에 시간이 걸립니다.

```sh
ssh ubuntu@SERVER_IP
sudo cloud-init status --wait
sudo systemctl status openstack-vdi-server
sudo docker compose -f /opt/openstack-vdi/compose.yaml --env-file /opt/openstack-vdi/.env ps
sudo cat /var/lib/openstack-vdi/rustdesk/id_ed25519.pub
```

Windows VM과 사용자 단말의 RustDesk 네트워크 설정에 다음을 적용합니다.

- ID Server: `SERVER_IP:21116`
- Relay Server: `SERVER_IP:21117`
- Key: 위 `id_ed25519.pub` 내용 (공개키)
- API Server: 비움 (OSS 서버)

개인키 `id_ed25519`는 서버 밖에 공개하지 않습니다. ID 데이터베이스와 키는
`/var/lib/openstack-vdi/rustdesk`에 유지됩니다. VM 삭제 전에는 별도 백업이 필요합니다.
서버 키는 클라이언트의 서버 확인에 쓰이며, 사용자별 VM 접속 권한을 대체하지 않습니다.

네이티브 클라이언트용 TCP 21115–21117, UDP 21116만 지정한 CIDR에서 허용합니다.
웹 클라이언트용 포트는 열지 않습니다. 이는 단일 테스트망 구성이고, 업무망/폐쇄망의
정책 강제와 분리된 서버 구성은 이후 단계입니다.
