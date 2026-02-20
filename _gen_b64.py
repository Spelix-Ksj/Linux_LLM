
import base64

lines = []
def a(s):
    lines.append(s)

a('#!/usr/bin/env python3')
a('"""deploy_fixes.py - Deploy fixed text2sql files to Linux server and verify."""')
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
a('    (r"D:\Dev\Linux_LLM\app\text2sql_pipeline.py", "/root/text2sql/text2sql_pipeline.py"),')
a('    (r"D:\Dev\Linux_LLM\app\app.py",               "/root/text2sql/app.py"),')
a('    (r"D:\Dev\Linux_LLM\app\db_setup.py",           "/root/text2sql/db_setup.py"),')
a('    (r"D:\Dev\Linux_LLM\app\.env",                  "/root/text2sql/.env"),')
a(']')

content = '\n'.join(lines)
print(base64.b64encode(content.encode()).decode())
