import base64
import re

with open("app/frontend/assets/z17.png", "rb") as f:
    b64 = base64.b64encode(f.read()).decode("utf-8")

with open("app/frontend/landing_template.py", "r", encoding="utf-8") as f:
    content = f.read()

new_content = re.sub(
    r"Z17_IMAGE_B64 = .*",
    f'Z17_IMAGE_B64 = """data:image/png;base64,{b64}"""',
    content,
    flags=re.DOTALL,
)

with open("app/frontend/landing_template.py", "w", encoding="utf-8") as f:
    f.write(new_content)
