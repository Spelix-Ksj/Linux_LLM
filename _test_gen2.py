import pathlib

lines = []
a = lines.append

a('#!/usr/bin/env python3')
a('"""deploy_fixes.py - Deploy fixed text2sql files to Linux server and verify.')
a('CRITICAL: Does NOT touch the existing vLLM process on GPUs 0-3."""')
a('')
a('import sys')
a('import time')
a('import paramiko')
a('')
a('HOST = "192.168.10.40"')
a('PORT = 22')
a('USER = "root"')
a('PASS = os.environ.get("SSH_PASSWORD", "")')
a('')
a('UPLOADS = [')
a('    (r"D:\\Dev\\Linux_LLM\x07pp\text2sql_pipeline.py", "/root/text2sql/text2sql_pipeline.py"),')
a('    (r"D:\\Dev\\Linux_LLM\x07pp\x07pp.py",               "/root/text2sql/app.py"),')
a('    (r"D:\\Dev\\Linux_LLM\x07pp\\db_setup.py",           "/root/text2sql/db_setup.py"),')
a('    (r"D:\\Dev\\Linux_LLM\x07pp\\.env",                  "/root/text2sql/.env"),')
a(']')