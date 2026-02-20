import pathlib

lines = []
a = lines.append

a('#!/usr/bin/env python3')
a('"""deploy_fixes.py - Deploy fixed text2sql files to Linux server and verify."""')
a('')
a('import sys')
a('import time')
a('import paramiko')
a('')