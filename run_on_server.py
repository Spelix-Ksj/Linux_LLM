"""
원격 서버에서 명령 실행 (Git Bash 경로 변환 문제 회피용)
명령을 Python 문자열로 직접 전달
"""
import os
import paramiko
import sys

SERVER = "192.168.10.40"
USER = "root"
PASSWORD = os.environ.get("SSH_PASSWORD", "")


def run_commands(commands, timeout=600):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(SERVER, port=22, username=USER, password=PASSWORD, timeout=15)

    results = []
    for cmd in commands:
        print(f"\n{'='*60}")
        print(f"[CMD] {cmd}")
        print('='*60)
        stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        exit_code = stdout.channel.recv_exit_status()
        if out.strip():
            print(out.strip())
        if err.strip():
            print(f"[STDERR] {err.strip()}")
        if exit_code != 0:
            print(f"[EXIT CODE] {exit_code}")
        results.append((out, err, exit_code))

    client.close()
    return results


if __name__ == "__main__":
    # 파일에서 명령 읽기 모드
    if len(sys.argv) > 1 and sys.argv[1] == "--file":
        with open(sys.argv[2], encoding="utf-8") as f:
            cmds = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        run_commands(cmds)
    else:
        # 인라인 명령
        run_commands(sys.argv[1:])
