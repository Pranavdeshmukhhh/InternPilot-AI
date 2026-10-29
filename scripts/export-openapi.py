"""Export API contracts without reading user state or making provider calls."""
import json
import os
import sys
import tempfile
from pathlib import Path
from cryptography.fernet import Fernet

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="internpilot-contract-") as directory:
    os.environ.update(DATA_DIR=directory, DATABASE_URL="sqlite:///:memory:", ENCRYPTION_KEY=Fernet.generate_key().decode(),
        ENVIRONMENT="development", REDIS_URL="", LLM_PROVIDER="disabled", TEST_MODE="false")
    sys.path.insert(0, str(root / "backend"))
    from app.main import app
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "frontend/openapi.json"
    target.write_text(json.dumps(app.openapi(), indent=2) + "\n")
