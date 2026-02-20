#!/usr/bin/env python3
"""
Deployment Verification Script for server 192.168.10.40
Checks: vLLM, Gradio UI, DB connection, End-to-end Text2SQL
"""

import os
import paramiko
import sys
import time

HOST = "192.168.10.40"
USER = "root"
PASSWORD = os.environ.get("SSH_PASSWORD", "")
SSH_TIMEOUT = 10
CMD_TIMEOUT = 60

def create_ssh_client():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=SSH_TIMEOUT)
    return client

def run_cmd(client, cmd, timeout=CMD_TIMEOUT):
    """Run a command over SSH and return (stdout, stderr, exit_code)."""
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    return out, err, exit_code

def print_banner(title):
    width = 60
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)

def print_result(name, passed, detail=""):
    tag = "PASS" if passed else "FAIL"
    marker = "[v]" if passed else "[X]"
    print(f"  {marker} {name}: {tag}")
    if detail:
        for line in detail.strip().splitlines():
            print(f"      {line}")

def main():
    results = []  # list of (name, passed)

    print("Connecting to %s as %s ..." % (HOST, USER))
    try:
        client = create_ssh_client()
    except Exception as e:
        print("FATAL: SSH connection failed: %s" % e)
        sys.exit(1)
    print("SSH connection established.\n")

    # ------------------------------------------------------------------
    # 1. vLLM Health Check
    # ------------------------------------------------------------------
    print_banner("1. vLLM Health Check")

    # 1a. Model list endpoint
    out, err, rc = run_cmd(client, "curl -s http://localhost:8000/v1/models")
    models_ok = rc == 0 and '"id"' in out and '"object"' in out
    detail = out[:300] if out else (err[:300] if err else "(no output)")
    print_result("vLLM /v1/models endpoint", models_ok, detail)
    results.append(("vLLM /v1/models endpoint", models_ok))

    # 1b. GPU memory usage
    out, err, rc = run_cmd(client,
        "nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv")
    gpu_lines = [l for l in out.splitlines() if l and not l.startswith("index")]
    high_mem_count = 0
    for line in gpu_lines:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2:
            mem_str = parts[1].replace("MiB", "").strip()
            try:
                mem_used = int(mem_str)
                if mem_used > 1000:  # >1 GB counts as "high"
                    high_mem_count += 1
            except ValueError:
                pass
    gpus_ok = high_mem_count >= 4  # GPUs 0-3 all showing high memory
    detail = out if out else (err if err else "(no output)")
    print_result("GPU memory (expect GPUs 0-3 high usage)", gpus_ok,
                 detail + "\n      -> %d / 4 GPUs with >1 GB used" % high_mem_count)
    results.append(("GPU memory usage", gpus_ok))

    # ------------------------------------------------------------------
    # 2. Gradio UI Check
    # ------------------------------------------------------------------
    print_banner("2. Gradio UI Check")

    # 2a. HTTP 200
    out, err, rc = run_cmd(client,
        "curl -s -o /dev/null -w '%{http_code}' http://localhost:7860")
    http_ok = out.strip() == "200"
    print_result("Gradio HTTP status (expect 200)", http_ok, "Got: %s" % out.strip())
    results.append(("Gradio HTTP 200", http_ok))

    # 2b. systemd service active
    out, err, rc = run_cmd(client, "systemctl is-active text2sql-ui")
    svc_ok = out.strip() == "active"
    print_result("text2sql-ui service active", svc_ok, "Got: %s" % out.strip())
    results.append(("text2sql-ui service", svc_ok))

    # ------------------------------------------------------------------
    # 3. DB Connection Check
    # ------------------------------------------------------------------
    print_banner("3. DB Connection Check")

    db_cmd = (
        'cd /root/text2sql && /root/miniconda3/envs/text2sql/bin/python -c '
        '"from db_setup import get_engine; from sqlalchemy import text; '
        'e=get_engine(); r=e.connect().execute(text(\'SELECT 1 FROM dual\')); '
        'print(\'DB OK:\', r.fetchone())"'
    )
    out, err, rc = run_cmd(client, db_cmd)
    db_ok = rc == 0 and "DB OK:" in out
    detail = out if out else (err[:500] if err else "(no output)")
    print_result("Oracle DB connection", db_ok, detail)
    results.append(("DB connection", db_ok))

    # ------------------------------------------------------------------
    # 4. End-to-End Text2SQL Test
    # ------------------------------------------------------------------
    print_banner("4. End-to-End Text2SQL Test")

    e2e_cmd = (
        'cd /root/text2sql && /root/miniconda3/envs/text2sql/bin/python -c '
        '"from text2sql_pipeline import ask_hr; '
        "r=ask_hr('move_item_master 테이블의 전체 행 수를 알려줘'); "
        "print('SQL:', r['sql']); "
        "print('Error:', r['error']); "
        "print('Rows:', len(r['result']))\""
    )
    out, err, rc = run_cmd(client, e2e_cmd, timeout=120)

    # Parse output
    has_sql = "SQL:" in out
    error_line = [l for l in out.splitlines() if l.startswith("Error:")]
    error_val = error_line[0].split("Error:", 1)[1].strip() if error_line else "unknown"
    no_error = error_val in ("None", "")
    rows_line = [l for l in out.splitlines() if l.startswith("Rows:")]
    rows_val = 0
    if rows_line:
        try:
            rows_val = int(rows_line[0].split("Rows:", 1)[1].strip())
        except ValueError:
            pass
    has_rows = rows_val > 0

    e2e_ok = rc == 0 and has_sql and no_error and has_rows
    detail = out if out else (err[:800] if err else "(no output)")
    print_result("Text2SQL end-to-end", e2e_ok, detail)
    results.append(("Text2SQL end-to-end", e2e_ok))

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    client.close()

    print_banner("SUMMARY")
    total = len(results)
    passed = sum(1 for _, p in results if p)
    failed = total - passed
    for name, p in results:
        tag = "PASS" if p else "FAIL"
        marker = "[v]" if p else "[X]"
        print(f"  {marker} {name}: {tag}")

    print()
    print(f"  Total: {total}  |  Passed: {passed}  |  Failed: {failed}")

    if failed == 0:
        print("\n  >>> ALL CHECKS PASSED <<<")
    else:
        print("\n  >>> %d CHECK(S) FAILED <<<" % failed)

    sys.exit(0 if failed == 0 else 1)

if __name__ == "__main__":
    main()
