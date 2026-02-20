"""
원격 서버 파일 전송 및 배포 실행 스크립트
Python paramiko 기반 SSH/SFTP
"""
import os
import sys
import stat
import paramiko
import time

# 서버 접속 정보
SERVER = "192.168.10.40"
PORT = 22
USER = "root"
PASSWORD = os.environ.get("SSH_PASSWORD", "")
REMOTE_DIR = "/root/text2sql"

# 로컬 프로젝트 경로
LOCAL_BASE = os.path.dirname(os.path.abspath(__file__))


def create_ssh_client():
    """SSH 클라이언트 생성"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"[SSH] {USER}@{SERVER}:{PORT} 접속 중...")
    client.connect(SERVER, port=PORT, username=USER, password=PASSWORD, timeout=15)
    print("[SSH] 접속 성공!")
    return client


def exec_cmd(client, cmd, print_output=True):
    """원격 명령 실행"""
    print(f"\n[CMD] {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=600)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    exit_code = stdout.channel.recv_exit_status()

    if print_output:
        if out.strip():
            print(out.strip())
        if err.strip():
            print(f"[STDERR] {err.strip()}")
    if exit_code != 0:
        print(f"[EXIT CODE] {exit_code}")
    return out, err, exit_code


def upload_files(client):
    """SFTP로 파일 전송"""
    sftp = client.open_sftp()

    # 원격 디렉토리 생성
    for d in [REMOTE_DIR, f"{REMOTE_DIR}/deploy", f"{REMOTE_DIR}/services"]:
        try:
            sftp.stat(d)
        except FileNotFoundError:
            sftp.mkdir(d)
            print(f"[SFTP] 디렉토리 생성: {d}")

    uploaded = 0

    # deploy/ 스크립트 전송
    deploy_dir = os.path.join(LOCAL_BASE, "deploy")
    for f in os.listdir(deploy_dir):
        if f.endswith(".sh"):
            local = os.path.join(deploy_dir, f)
            remote = f"{REMOTE_DIR}/deploy/{f}"
            sftp.put(local, remote)
            sftp.chmod(remote, 0o755)
            print(f"[SFTP] {f} -> {remote}")
            uploaded += 1

    # services/ 파일 전송
    svc_dir = os.path.join(LOCAL_BASE, "services")
    for f in os.listdir(svc_dir):
        if f.endswith(".service"):
            local = os.path.join(svc_dir, f)
            remote = f"{REMOTE_DIR}/services/{f}"
            sftp.put(local, remote)
            print(f"[SFTP] {f} -> {remote}")
            uploaded += 1

    # app/ 파일 전송
    app_dir = os.path.join(LOCAL_BASE, "app")
    for f in os.listdir(app_dir):
        local = os.path.join(app_dir, f)
        if os.path.isfile(local):
            remote = f"{REMOTE_DIR}/{f}"
            sftp.put(local, remote)
            print(f"[SFTP] {f} -> {remote}")
            uploaded += 1

    sftp.close()
    print(f"\n[SFTP] 총 {uploaded}개 파일 전송 완료")


def run_deploy(client):
    """배포 스크립트 단계별 실행"""
    print("\n" + "=" * 60)
    print("  서버 배포 시작")
    print("=" * 60)

    # Step 1: 환경 확인
    print("\n>>> Step 1: 서버 환경 확인")
    exec_cmd(client, f"bash {REMOTE_DIR}/deploy/01_check_environment.sh")

    # Step 2: 시스템 패키지
    print("\n>>> Step 2: 시스템 패키지 설치")
    exec_cmd(client, f"bash {REMOTE_DIR}/deploy/02_install_system_deps.sh")

    # Step 3: Miniconda
    print("\n>>> Step 3: Miniconda 설치")
    exec_cmd(client, f"bash {REMOTE_DIR}/deploy/03_install_miniconda.sh")

    # Step 4: vLLM
    print("\n>>> Step 4: vLLM 설치")
    exec_cmd(client, f"bash {REMOTE_DIR}/deploy/04_install_vllm.sh")

    # Step 5: 앱 의존성
    print("\n>>> Step 5: 애플리케이션 의존성 설치")
    exec_cmd(client, f"bash {REMOTE_DIR}/deploy/05_install_app_deps.sh")

    # Step 6: 서비스 등록
    print("\n>>> Step 6: systemd 서비스 등록")
    exec_cmd(client, f"bash {REMOTE_DIR}/deploy/06_setup_services.sh")

    print("\n" + "=" * 60)
    print("  배포 완료!")
    print("=" * 60)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    client = create_ssh_client()
    try:
        if mode in ("upload", "all"):
            upload_files(client)
        if mode in ("deploy", "all"):
            run_deploy(client)
        if mode == "check":
            exec_cmd(client, f"bash {REMOTE_DIR}/deploy/01_check_environment.sh")
    finally:
        client.close()
        print("\n[SSH] 연결 종료")
