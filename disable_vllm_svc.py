#!/usr/bin/env python3
"""
disable_vllm_svc.py
====================
SSH into 192.168.10.40 and disable + mask the vllm.service and vllm-7b.service
so they cannot accidentally start (via boot or manual `systemctl start`) and
clobber the already-running vLLM process on GPUs 0-3.
"""

import os
import paramiko
import sys


HOST = "192.168.10.40"
PORT = 22
USER = "root"
PASSWORD = os.environ.get("SSH_PASSWORD", "")

# Each step: (description, command)
STEPS = [
    # ---- Disable (prevent auto-start on boot) ----
    ("Disable vllm.service (prevent auto-start on boot)",
     "systemctl disable vllm 2>/dev/null; true"),

    ("Disable vllm-7b.service (prevent auto-start on boot)",
     "systemctl disable vllm-7b 2>/dev/null; true"),

    # ---- Mask (prevent ANY start, manual or otherwise) ----
    ("Mask vllm.service (prevent manual start too)",
     "systemctl mask vllm 2>/dev/null; true"),

    ("Mask vllm-7b.service (prevent manual start too)",
     "systemctl mask vllm-7b 2>/dev/null; true"),

    # ---- Verify service states ----
    ("Verify vllm.service is-enabled state",
     "systemctl is-enabled vllm 2>&1"),

    ("Verify vllm-7b.service is-enabled state",
     "systemctl is-enabled vllm-7b 2>&1"),

    # ---- Verify existing processes still alive ----
    ("Verify existing vLLM is still running (GET /v1/models)",
     "curl -s http://localhost:8000/v1/models | head -c 100"),

    ("Verify Gradio is still running (HTTP status on :7860)",
     "curl -s -o /dev/null -w '%{http_code}' http://localhost:7860"),
]


def run_command(ssh_client, cmd):
    """Execute a command over SSH and return (stdout, stderr, exit_code)."""
    stdin, stdout, stderr = ssh_client.exec_command(cmd, timeout=15)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    return out, err, exit_code


def main():
    separator = "=" * 70

    print(separator)
    print("  DISABLE & MASK vllm / vllm-7b SERVICES")
    print(f"  Target: {USER}@{HOST}")
    print(separator)
    print()

    # -- Connect ----------------------------------------------------------
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        print(f"[CONNECT] Connecting to {HOST}:{PORT} as {USER} ...")
        ssh.connect(HOST, port=PORT, username=USER, password=PASSWORD,
                    timeout=10, allow_agent=False, look_for_keys=False)
        print(f"[CONNECT] SSH session established.\n")
    except Exception as exc:
        print(f"[ERROR]   Failed to connect: {exc}")
        return 1

    # -- Execute steps ----------------------------------------------------
    all_ok = True

    for idx, (description, cmd) in enumerate(STEPS, start=1):
        print(f"--- Step {idx}/{len(STEPS)}: {description}")
        print(f"    CMD: {cmd}")

        try:
            out, err, rc = run_command(ssh, cmd)
        except Exception as exc:
            print(f"    [ERROR] Exception during execution: {exc}\n")
            all_ok = False
            continue

        # Display output
        if out:
            print(f"    STDOUT: {out}")
        if err:
            print(f"    STDERR: {err}")
        print(f"    EXIT CODE: {rc}")

        # Interpret verification steps
        if "is-enabled" in cmd:
            if "masked" in (out + err).lower():
                print("    [OK] Service is MASKED -- cannot be started.")
            elif "disabled" in (out + err).lower():
                print("    [WARN] Service is disabled but NOT masked.")
                all_ok = False
            else:
                print(f"    [INFO] State: {out or err}")

        if "/v1/models" in cmd:
            if out and ("model" in out.lower() or "data" in out.lower()):
                print("    [OK] vLLM API is responding -- existing process is alive.")
            else:
                print("    [WARN] vLLM API did not return expected model data.")
                all_ok = False

        if "http_code" in cmd:
            if out == "200":
                print("    [OK] Gradio returned HTTP 200 -- still running.")
            else:
                print(f"    [WARN] Gradio returned HTTP {out} (expected 200).")
                all_ok = False

        print()

    # -- Summary ----------------------------------------------------------
    ssh.close()

    print(separator)
    if all_ok:
        print("  ALL STEPS COMPLETED SUCCESSFULLY.")
        print("  Both vllm.service and vllm-7b.service are MASKED.")
        print("  Running `systemctl start vllm` will now REFUSE to start.")
        print("  Existing vLLM process on GPUs 0-3 is unaffected.")
    else:
        print("  COMPLETED WITH WARNINGS -- review output above.")
    print(separator)

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
