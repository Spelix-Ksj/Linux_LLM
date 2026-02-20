#!/usr/bin/env python3
"""
deploy_fixes.py - Deploy fixed text2sql files to Linux server and verify.
CRITICAL: Does NOT touch the existing vLLM process on GPUs 0-3.
"""

import os
import sys
import time
import paramiko

HOST = "192.168.10.40"
PORT = 22
USER = "root"
PASS = os.environ.get("SSH_PASSWORD", "")

UPLOADS = [
    (r"D:\Dev\Linux_LLM\app\text2sql_pipeline.py", "/root/text2sql/text2sql_pipeline.py"),
    (r"D:\Dev\Linux_LLM\app\app.py",               "/root/text2sql/app.py"),
    (r"D:\Dev\Linux_LLM\app\db_setup.py",           "/root/text2sql/db_setup.py"),
    (r"D:\Dev\Linux_LLM\app\.env",                  "/root/text2sql/.env"),
]


def ssh_exec(client, cmd, timeout=60):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    if err and not out:
        return err
    if err:
        return out + "\n" + err
    return out


def banner(title):
    print()
    print("=" * 64)
    print(f"  {title}")
    print("=" * 64)


def upload_via_sftp(client, results):
    banner("STEP 1 - UPLOAD FIXED FILES VIA SFTP")
    sftp = client.open_sftp()
    try:
        sftp.stat("/root/text2sql")
    except FileNotFoundError:
        sftp.mkdir("/root/text2sql")
        print("[INFO] Created /root/text2sql/")

    for local_path, remote_path in UPLOADS:
        try:
            sftp.put(local_path, remote_path)
            remote_stat = sftp.stat(remote_path)
            fname = remote_path.split("/")[-1]
            print(f"[OK] Uploaded {local_path}")
            print(f"     -> {remote_path}  ({remote_stat.st_size} bytes)")
            results.append((f"Upload {fname}", "PASS", f"{remote_stat.st_size} bytes"))
        except Exception as e:
            fname = remote_path.split("/")[-1]
            print(f"[FAIL] Upload failed for {local_path}: {e}")
            results.append((f"Upload {fname}", "FAIL", str(e)))
    sftp.close()


def restart_service(client):
    banner("STEP 2 - RESTART GRADIO SERVICE (text2sql-ui)")
    print("[INFO] Running: systemctl restart text2sql-ui")
    out = ssh_exec(client, "systemctl restart text2sql-ui", timeout=30)
    if out:
        print(out)
    print("[INFO] Waiting 10 seconds for service to start...")
    time.sleep(10)
    print("[INFO] Running: systemctl status text2sql-ui")
    out = ssh_exec(client, "systemctl status text2sql-ui 2>&1 | head -10")
    print(out)


def verify_all(client, results):
    banner("STEP 3 - FULL VERIFICATION")

    # Check 1
    print("\n--- Check 1: systemctl is-active text2sql-ui ---")
    out = ssh_exec(client, "systemctl is-active text2sql-ui")
    status = "PASS" if out.strip() == "active" else "FAIL"
    print(f"  Result: {out!r}  -> {status}")
    results.append(("Service active", status, out.strip()))

    # Check 2
    print("\n--- Check 2: Gradio HTTP 200 on port 7860 ---")
    out = ssh_exec(client, "curl -s -o /dev/null -w '%{http_code}' http://localhost:7860")
    status = "PASS" if out.strip() == "200" else "FAIL"
    print(f"  HTTP status code: {out!r}  -> {status}")
    results.append(("Gradio HTTP 200", status, f"HTTP {out.strip()}"))

    # Check 3
    print("\n--- Check 3: vLLM /v1/models endpoint ---")
    cmd_vllm = (
        "curl -s http://localhost:8000/v1/models | "
        "python3 -c 'import sys,json; d=json.load(sys.stdin); print(d[\"data\"][0][\"id\"])'"
    )
    out = ssh_exec(client, cmd_vllm)
    if out and "error" not in out.lower() and "traceback" not in out.lower():
        status = "PASS"
    else:
        status = "FAIL"
    print(f"  Model name: {out!r}  -> {status}")
    results.append(("vLLM alive", status, out.strip()))

    # Check 4: End-to-end test
    print("\n--- Check 4: End-to-end ask_hr() test ---")
    e2e_py = (
        "from text2sql_pipeline import ask_hr\n"
        "r = ask_hr('move_item_master\uc5d0\uc11c \uc131\ubcc4(gender_nm)\ubcc4 \uc778\uc6d0\uc218\ub97c \uad6c\ud574\uc918')\n"
        "print('SQL:', r['sql'])\n"
        "print('Error:', r['error'])\n"
        "print('Rows:', len(r['result']) if r['result'] is not None else 0)\n"
        "if r['result'] is not None and len(r['result']) > 0:\n"
        "    print(r['result'].to_string(index=False))\n"
    )
    sftp = client.open_sftp()
    with sftp.file("/root/text2sql/_e2e_test.py", "w") as f:
        f.write(e2e_py)
    sftp.close()
    e2e_cmd = "cd /root/text2sql && /root/miniconda3/envs/text2sql/bin/python /root/text2sql/_e2e_test.py"
    out = ssh_exec(client, e2e_cmd, timeout=120)
    print(out)
    has_sql = "SQL:" in out and len(out.split("SQL:")[1].strip()) > 0
    has_rows = "Rows:" in out
    error_line = ""
    for line in out.splitlines():
        if line.startswith("Error:"):
            error_line = line.split("Error:")[1].strip()
    no_error = error_line in ("None", "")
    if has_sql and has_rows and no_error:
        status = "PASS"
        detail = "Query returned results, no error"
    else:
        status = "FAIL"
        detail = f"sql_ok={has_sql}, rows_ok={has_rows}, error={error_line!r}"
    print(f"  -> {status}: {detail}")
    results.append(("E2E ask_hr()", status, detail))

    # Check 5: SQL safety guard
    print("\n--- Check 5: SQL safety guard (_is_safe_sql) ---")
    safety_py = (
        "from text2sql_pipeline import _is_safe_sql\n"
        "tests = [\n"
        "    ('SELECT * FROM t', True),\n"
        "    ('DELETE FROM t', False),\n"
        "    ('SELECT * FROM (DELETE FROM t)', False),\n"
        "    ('SELECT 1; DROP TABLE t', False),\n"
        "    ('WITH x AS (SELECT 1) SELECT * FROM x', True),\n"
        "]\n"
        "all_pass = True\n"
        "for sql, expected in tests:\n"
        "    result = _is_safe_sql(sql)\n"
        "    st = 'PASS' if result == expected else 'FAIL'\n"
        "    if st == 'FAIL': all_pass = False\n"
        "    print(f'{st}: _is_safe_sql({sql!r}) = {result} (expected {expected})')\n"
        "print('ALL_PASS' if all_pass else 'SOME_FAIL')\n"
    )
    sftp = client.open_sftp()
    with sftp.file("/root/text2sql/_safety_test.py", "w") as f:
        f.write(safety_py)
    sftp.close()
    safety_cmd = "cd /root/text2sql && /root/miniconda3/envs/text2sql/bin/python /root/text2sql/_safety_test.py"
    out = ssh_exec(client, safety_cmd, timeout=30)
    print(out)
    status = "PASS" if "ALL_PASS" in out else "FAIL"
    fail_count = out.count("FAIL:")
    pass_count = out.count("PASS:")
    detail = f"{pass_count} passed, {fail_count} failed"
    print(f"  -> {status}: {detail}")
    results.append(("SQL safety guard", status, detail))

    # Check 6
    print("\n--- Check 6: vllm.service is masked ---")
    out = ssh_exec(client, "systemctl is-enabled vllm 2>&1")
    status = "PASS" if out.strip() == "masked" else "FAIL"
    print(f"  Result: {out!r}  -> {status}")
    results.append(("vllm masked", status, out.strip()))


def print_summary(results):
    banner("FINAL SUMMARY")
    h = "#"
    ck = "Check"
    st_h = "Status"
    print(f"{h:<4} {ck:<30} {st_h:<8} Detail")
    print("-" * 80)
    all_ok = True
    for i, (name, st, detail) in enumerate(results, 1):
        print(f"{i:<4} {name:<30} {st:<8} {detail}")
        if st != "PASS":
            all_ok = False
    print("-" * 80)
    if all_ok:
        print("ALL CHECKS PASSED - Deployment successful.")
    else:
        print("SOME CHECKS FAILED - Review output above.")
    print()
    return all_ok


def main():
    results = []
    banner("CONNECTING TO SERVER")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)
    except Exception as e:
        print(f"[FATAL] SSH connection failed: {e}")
        sys.exit(1)
    print(f"[OK] Connected to {USER}@{HOST}")

    upload_via_sftp(client, results)
    restart_service(client)
    verify_all(client, results)
    all_ok = print_summary(results)

    client.close()
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
