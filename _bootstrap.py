import pathlib, base64, sys
data = sys.stdin.read().strip()
content = base64.b64decode(data).decode("utf-8")
out = pathlib.Path("D:/Dev/Linux_LLM/deploy_fixes.py")
out.write_text(content, encoding="utf-8")
print(f"Wrote {len(content)} bytes to {out}")
