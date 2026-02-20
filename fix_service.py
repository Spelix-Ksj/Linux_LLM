#!/usr/bin/env python3
"""
fix_service.py - Fix the masked text2sql-ui.service on Rocky Linux 9.6
Uses paramiko SSH/SFTP to:
  1. Upload a corrected systemd service file
  2. Unmask, reload, and start the service
  3. Fall back to nohup if systemd start fails (e.g. SELinux)
  4. Verify vLLM is still running (GPUs 0-3 untouched)
"""

import os
import sys
import time
import paramiko

# -- Connection details ---------------------------------------------------
HOST = "192.168.10.40"
PORT = 22
USER = "root"
PASSWORD = os.environ.get("SSH_PASSWORD", "")

# -- Service file content -------------------------------------------------
SERVICE_FILE_CONTENT = """\
[Unit]
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

SERVICE_FILE_PATH = "/etc/systemd/system/text2sql-ui.service"


def create_ssh_client():
    """Create and return a connected paramiko SSH client."""
    print(f"[*] Connecting to {USER}@{HOST}:{PORT} ...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=15)
    print("[+] SSH connection established.")
    return client


def run_cmd(client, cmd, description=None, check=False):
    """
    Execute a command over SSH.  Returns (exit_code, stdout, stderr).
    If *check* is True, raises RuntimeError on non-zero exit.
    """
    label = description or cmd
    print(f"\n{'='*60}")
    print(f"[CMD] {label}")
    print(f"  >>> {cmd}")
    print("-" * 60)

    stdin, stdout, stderr = client.exec_command(cmd, timeout=120)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")

    if out:
        print(out.rstrip())
    if err:
        print(f"[STDERR] {err.rstrip()}")
    print(f"[EXIT CODE] {exit_code}")

    if check and exit_code != 0:
        raise RuntimeError(f"Command failed (exit {exit_code}): {cmd}")

    return exit_code, out, err


def upload_service_file(client):
    """Upload the corrected service file via SFTP."""
    print(f"\n[*] Uploading service file to {SERVICE_FILE_PATH} via SFTP ...")
    sftp = client.open_sftp()
    try:
        with sftp.file(SERVICE_FILE_PATH, "w") as f:
            f.write(SERVICE_FILE_CONTENT)
        # Verify it landed
        stat = sftp.stat(SERVICE_FILE_PATH)
        print(f"[+] Upload complete. File size: {stat.st_size} bytes")
    finally:
        sftp.close()


def step_systemd_fix(client):
    """
    Step 3 -- unmask, reload, reset-failed, start, then check.
    Returns True if the service is running and HTTP 200 on :7860.
    """
    commands = [
        ("systemctl unmask text2sql-ui",                        "Unmask the service"),
        ("systemctl daemon-reload",                             "Reload systemd daemon"),
        ("systemctl reset-failed text2sql-ui 2>/dev/null; true","Reset failed state"),
        ("systemctl start text2sql-ui",                         "Start text2sql-ui"),
    ]

    for cmd, desc in commands:
        run_cmd(client, cmd, description=desc)

    # Give it time to start
    print("\n[*] Waiting 10 seconds for service to stabilise ...")
    time.sleep(10)

    # Status & logs
    rc_status, out_status, _ = run_cmd(client, "systemctl status text2sql-ui",
                                       description="Check service status")
    run_cmd(client, "journalctl -u text2sql-ui -n 20 --no-pager",
            description="Last 20 journal lines")

    # HTTP check
    rc_curl, out_curl, _ = run_cmd(
        client,
        "curl -s -o /dev/null -w '%{http_code}' http://localhost:7860",
        description="HTTP check on port 7860",
    )

    http_code = out_curl.strip()
    service_ok = rc_status == 0 and "active (running)" in out_status
    http_ok = http_code == "200"

    print(f"\n[*] Service running: {service_ok}  |  HTTP 7860 response: {http_code}")
    return service_ok and http_ok


def step_nohup_fallback(client):
    """
    Step 4 -- If systemd failed (likely SELinux), fall back to nohup.
    Returns True if HTTP 200 on :7860.
    """
    print("\n" + "#" * 60)
    print("# FALLBACK: Starting Gradio via nohup (bypass systemd/SELinux)")
    print("#" * 60)

    run_cmd(client, "systemctl stop text2sql-ui 2>/dev/null; true",
            description="Stop systemd unit (best-effort)")

    # Also kill any lingering python app.py to avoid port conflicts
    run_cmd(client,
            "pkill -f 'python app.py' 2>/dev/null; sleep 2; true",
            description="Kill lingering app.py processes")

    nohup_cmd = (
        "cd /root/text2sql && "
        "nohup /root/miniconda3/envs/text2sql/bin/python app.py "
        "> /root/text2sql/gradio.log 2>&1 &"
    )
    run_cmd(client, nohup_cmd, description="Start Gradio with nohup")

    print("\n[*] Waiting 10 seconds for Gradio to start ...")
    time.sleep(10)

    rc_curl, out_curl, _ = run_cmd(
        client,
        "curl -s -o /dev/null -w '%{http_code}' http://localhost:7860",
        description="HTTP check on port 7860",
    )

    run_cmd(client, "tail -30 /root/text2sql/gradio.log",
            description="Last 30 lines of gradio.log")

    http_code = out_curl.strip()
    print(f"\n[*] HTTP 7860 response: {http_code}")
    return http_code == "200"


def step_verify_vllm(client):
    """Step 5 -- Confirm vLLM on GPUs 0-3 is untouched."""
    print("\n" + "#" * 60)
    print("# VERIFY: vLLM still running (MUST NOT be affected)")
    print("#" * 60)
    rc, out, _ = run_cmd(
        client,
        "curl -s http://localhost:8000/v1/models | head -1",
        description="Check vLLM /v1/models endpoint",
    )
    if rc == 0 and out.strip():
        print("[+] vLLM is responding. All good.")
    else:
        print("[!] WARNING: vLLM did not respond. Investigate immediately!")


def main():
    client = None
    try:
        # -- Step 1: SSH connect ------------------------------------------
        client = create_ssh_client()

        # -- Step 2: Upload service file via SFTP -------------------------
        upload_service_file(client)

        # -- Step 3: systemd unmask / reload / start ----------------------
        success = step_systemd_fix(client)

        # -- Step 4: Fallback if systemd failed ---------------------------
        if not success:
            print("\n[!] systemd start did NOT succeed. Trying nohup fallback ...")
            success = step_nohup_fallback(client)
            if success:
                print("\n[+] Gradio is UP via nohup fallback.")
            else:
                print("\n[!] Gradio is NOT reachable even after fallback.")
        else:
            print("\n[+] text2sql-ui.service is running and Gradio is UP.")

        # -- Step 5: Verify vLLM untouched --------------------------------
        step_verify_vllm(client)

        # -- Summary ------------------------------------------------------
        print("\n" + "=" * 60)
        if success:
            print("[RESULT] SUCCESS - Gradio Text2SQL UI is reachable on port 7860.")
        else:
            print("[RESULT] FAILURE - Gradio could not be started. Review logs above.")
        print("=" * 60)

        return 0 if success else 1

    except Exception as exc:
        print(f"\n[FATAL] {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2

    finally:
        if client:
            client.close()
            print("\n[*] SSH connection closed.")


if __name__ == "__main__":
    sys.exit(main())
