#!/usr/bin/env python3
"""
Deployment script: Upload updated files and restart Gradio service.
CRITICAL: Does NOT touch the existing vLLM process on GPUs 0-3.
"""

import os
import paramiko
import sys
import time
import traceback
import io

# Fix Windows console encoding for Korean/emoji output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ---------- Configuration ----------
HOST = "192.168.10.40"
PORT = 22
USER = "root"
PASSWORD = os.environ.get("SSH_PASSWORD", "")

LOCAL_FILES = {
    r"D:\Dev\Linux_LLM\app\text2sql_pipeline.py": "/root/text2sql/text2sql_pipeline.py",
    r"D:\Dev\Linux_LLM\app\app.py": "/root/text2sql/app.py",
}

results = {}  # step_name -> (PASS|FAIL, detail)


def banner(title: str):
    line = "=" * 60
    print(f"\n{line}")
    print(f"  {title}")
    print(line)


def ssh_connect():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=15)
    return client


def run_cmd(client, cmd, timeout=120):
    """Run a command over SSH and return (exit_code, stdout, stderr)."""
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    return exit_code, out, err


# ==================================================================
# STEP 1 : Upload files via SFTP
# ==================================================================
def step1_upload(client):
    banner("STEP 1: Upload updated files via SFTP")
    sftp = client.open_sftp()
    all_ok = True
    for local_path, remote_path in LOCAL_FILES.items():
        try:
            print(f"  Uploading {local_path}")
            print(f"       -> {remote_path}")
            sftp.put(local_path, remote_path)
            # Verify by stat
            info = sftp.stat(remote_path)
            print(f"       OK  (size={info.st_size} bytes)")
        except Exception as e:
            print(f"       FAILED: {e}")
            all_ok = False
    sftp.close()
    if all_ok:
        results["Step 1 - SFTP Upload"] = ("PASS", "All files uploaded successfully")
        print("\n  [PASS] Step 1 - SFTP Upload")
    else:
        results["Step 1 - SFTP Upload"] = ("FAIL", "One or more uploads failed")
        print("\n  [FAIL] Step 1 - SFTP Upload")


# ==================================================================
# STEP 2 : Restart Gradio service
# ==================================================================
def step2_restart(client):
    banner("STEP 2: Restart Gradio service (text2sql-ui)")

    # Restart
    print("  Running: systemctl restart text2sql-ui")
    rc, out, err = run_cmd(client, "systemctl restart text2sql-ui", timeout=30)
    print(f"  exit_code={rc}")
    if err.strip():
        print(f"  stderr: {err.strip()}")

    # Sleep
    sleep_secs = 12
    print(f"  Sleeping {sleep_secs}s for module imports and DB connection...")
    time.sleep(sleep_secs)

    # Status
    print("  Running: systemctl status text2sql-ui")
    rc2, out2, err2 = run_cmd(client, "systemctl status text2sql-ui 2>&1 | head -10")
    print(out2)

    if rc == 0 and "active (running)" in out2.lower():
        results["Step 2 - Restart Gradio"] = ("PASS", "Service restarted and running")
        print("  [PASS] Step 2 - Restart Gradio")
    else:
        results["Step 2 - Restart Gradio"] = ("FAIL", f"restart rc={rc}, status output see above")
        print("  [FAIL] Step 2 - Restart Gradio")


# ==================================================================
# STEP 3 : Verification
# ==================================================================
def step3_verify(client):
    banner("STEP 3: Verify everything works")

    # --- 3a: Gradio HTTP check ---
    print("  3a) Checking Gradio HTTP (port 7860)...")
    rc, out, err = run_cmd(client, "curl -s -o /dev/null -w '%{http_code}' http://localhost:7860")
    http_code = out.strip()
    print(f"      HTTP status code: {http_code}")
    if http_code == "200":
        results["Step 3a - Gradio HTTP"] = ("PASS", f"HTTP {http_code}")
        print("      [PASS] Step 3a - Gradio HTTP")
    else:
        results["Step 3a - Gradio HTTP"] = ("FAIL", f"HTTP {http_code}")
        print("      [FAIL] Step 3a - Gradio HTTP")

    # --- 3b: vLLM still alive ---
    print("\n  3b) Checking vLLM (port 8000)...")
    rc, out, err = run_cmd(client, "curl -s http://localhost:8000/v1/models | head -c 80")
    print(f"      Response: {out}")
    if out.strip() and "error" not in out.lower():
        results["Step 3b - vLLM alive"] = ("PASS", out.strip()[:80])
        print("      [PASS] Step 3b - vLLM alive")
    else:
        results["Step 3b - vLLM alive"] = ("FAIL", out.strip()[:80] if out.strip() else "No response")
        print("      [FAIL] Step 3b - vLLM alive")

    # --- 3c: End-to-end Python test ---
    print("\n  3c) End-to-end test (ask_hr + generate_report)...")
    test_script = """cd /root/text2sql && /root/miniconda3/envs/text2sql/bin/python -c "
import traceback
try:
    from text2sql_pipeline import ask_hr, generate_report
    r = ask_hr('move_item_master\uc5d0\uc11c \uc9c1\uae09\ubcc4(pos_grd_nm) \uc778\uc6d0\uc218\ub97c \uad6c\ud574\uc918')
    print('=== SQL ===')
    print(r['sql'])
    print('=== Error ===')
    print(r['error'])
    print('=== Rows ===')
    print(len(r['result']))
    print('=== Reasoning (first 200 chars) ===')
    print(repr(r.get('reasoning', '')[:200]))
    print('=== Report ===')
    report = generate_report('\uc9c1\uae09\ubcc4 \uc778\uc6d0\uc218\ub97c \uad6c\ud574\uc918', r['sql'], r['result'], r.get('reasoning', ''))
    print(report[:500])
    print('=== E2E_SUCCESS ===')
except Exception:
    traceback.print_exc()
    print('=== E2E_FAILED ===')
"
"""
    rc, out, err = run_cmd(client, test_script, timeout=180)
    full_output = out + err
    print(full_output)

    if "=== E2E_SUCCESS ===" in full_output:
        results["Step 3c - E2E Test"] = ("PASS", "ask_hr + generate_report succeeded")
        print("      [PASS] Step 3c - E2E Test")
    else:
        results["Step 3c - E2E Test"] = ("FAIL", "See output above for details")
        print("      [FAIL] Step 3c - E2E Test")


# ==================================================================
# MAIN
# ==================================================================
def main():
    print("Connecting to {}@{}:{}...".format(USER, HOST, PORT))
    try:
        client = ssh_connect()
    except Exception as e:
        print(f"SSH connection failed: {e}")
        sys.exit(1)
    print("Connected.\n")

    try:
        step1_upload(client)
        step2_restart(client)
        step3_verify(client)
    finally:
        client.close()

    # ---------- Final Summary ----------
    banner("DEPLOYMENT SUMMARY")
    all_pass = True
    for step_name, (status, detail) in results.items():
        marker = "PASS" if status == "PASS" else "FAIL"
        print(f"  [{marker}] {step_name}: {detail[:120]}")
        if status != "PASS":
            all_pass = False

    print()
    if all_pass:
        print("  >>> ALL STEPS PASSED - Deployment successful.")
    else:
        print("  >>> SOME STEPS FAILED - Review output above.")
    print()

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
