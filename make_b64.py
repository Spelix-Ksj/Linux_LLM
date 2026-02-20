import base64
import pathlib

# Read the deploy script template and base64 encode it
template = pathlib.Path("D:/Dev/Linux_LLM/deploy_template.py").read_bytes()
b64 = base64.b64encode(template).decode("ascii")
print(b64)
