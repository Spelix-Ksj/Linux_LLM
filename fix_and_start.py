"""
서비스 파일 복구 및 Gradio 앱 시작
"""
import os
import paramiko

SERVER = "192.168.10.40"
USER = "root"
PASSWORD = os.environ.get("SSH_PASSWORD", "")

SERVICE_CONTENT = """[Unit]
Description=Text2SQL Gradio Web UI
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/text2sql
Environment="PATH=/root/miniconda3/envs/text2sql/bin:/usr/local/bin:/usr/bin"
ExecStart=/bin/bash -c '/root/miniconda3/envs/text2sql/bin/python app.py'
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
"""

def run_cmd(client, cmd):
    print(f"[CMD] {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    code = stdout.channel.recv_exit_status()
    if out:
        print(out)
    if err:
        print(f"  [STDERR] {err}")
    if code != 0:
        print(f"  [EXIT] {code}")
    return out, err, code

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER, port=22, username=USER, password=PASSWORD, timeout=15)

# 1. SFTP로 서비스 파일 업로드
print("=== Step 1: 서비스 파일 복구 ===")
sftp = client.open_sftp()

# masked 상태 해제를 위해 직접 파일 쓰기
with sftp.open("/etc/systemd/system/text2sql-ui.service", "w") as f:
    f.write(SERVICE_CONTENT)
print("서비스 파일 작성 완료")
sftp.close()

# 2. systemd 재로드
print("\n=== Step 2: systemd 재설정 ===")
run_cmd(client, "systemctl unmask text2sql-ui 2>&1 || true")
run_cmd(client, "systemctl daemon-reload")
run_cmd(client, "systemctl stop text2sql-ui 2>&1 || true")
run_cmd(client, "systemctl reset-failed text2sql-ui 2>&1 || true")

# 3. 서비스 시작
print("\n=== Step 3: 서비스 시작 ===")
run_cmd(client, "systemctl start text2sql-ui")

# 4. 대기 후 확인
import time
print("\n=== Step 4: 시작 대기 (10초) ===")
time.sleep(10)
run_cmd(client, "systemctl status text2sql-ui 2>&1 | head -15")
run_cmd(client, "journalctl -u text2sql-ui -n 15 --no-pager 2>&1")
run_cmd(client, "curl -s -o /dev/null -w 'HTTP %{http_code}' http://localhost:7860 2>&1")

client.close()
