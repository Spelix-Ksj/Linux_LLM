import pathlib
import base64

# Base64 encoded deploy_fixes.py content will go here
B64 = "PLACEHOLDER"

content = base64.b64decode(B64).decode("utf-8")
out = pathlib.Path("D:/Dev/Linux_LLM/deploy_fixes.py")
out.write_text(content, encoding="utf-8")
print(f"Wrote {len(content)} bytes to {out}")