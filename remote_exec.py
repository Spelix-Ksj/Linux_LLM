"""
원격 서버 명령 실행 유틸리티
Usage: python remote_exec.py "command1" "command2" ...
"""
import os
import sys
import paramiko

SERVER = "192.168.10.40"
USER = "root"
PASSWORD = os.environ.get("SSH_PASSWORD", "")


def run(commands):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(SERVER, port=22, username=USER, password=PASSWORD, timeout=15)

    for cmd in commands:
        print(f"\n{'='*60}")
        print(f"[CMD] {cmd}")
        print('='*60)
        stdin, stdout, stderr = client.exec_command(cmd, timeout=600)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        exit_code = stdout.channel.recv_exit_status()
        if out.strip():
            print(out.strip())
        if err.strip():
            print(f"[STDERR] {err.strip()}")
        if exit_code != 0:
            print(f"[EXIT CODE] {exit_code}")

    client.close()


if __name__ == "__main__":
    run(sys.argv[1:])
