"""
Test configuration loading.
"""

from app.core.config import settings
from app.core.constants import SUPPORTED_EXTENSIONS

print("=" * 60)

print("Application :", settings.app_name)
print("Version     :", settings.app_version)

print()

print("Host        :", settings.host)
print("Port        :", settings.port)

print()

print("Workspace   :", settings.workspace_dir)
print("Upload Limit:", settings.max_upload_mb, "MB")

print()

print("LLM Model   :", settings.ollama_model)

print()

print("Extensions  :", SUPPORTED_EXTENSIONS)

print("=" * 60)
