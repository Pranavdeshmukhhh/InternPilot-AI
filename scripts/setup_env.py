"""Create local secrets without printing them; safe to run repeatedly."""
from __future__ import annotations

import base64
import os
from pathlib import Path
import re
import secrets


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    env_path = root / ".env"
    content = env_path.read_text(encoding="utf-8") if env_path.exists() else (root / ".env.example").read_text(encoding="utf-8")
    generated = {
        "ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "POSTGRES_PASSWORD": secrets.token_hex(32),
        "REDIS_PASSWORD": secrets.token_hex(32),
    }
    for key, value in generated.items():
        pattern = rf"(?m)^{key}=([^\r\n]*)\r?$"
        match = re.search(pattern, content)
        if match is None:
            content += f"\n{key}={value}\n"
        elif not match.group(1).strip():
            content = re.sub(pattern, lambda _match: f"{key}={value}", content)
    fd = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(content)
    if os.name != "nt":
        env_path.chmod(0o600)
    print("Configuration is ready. Secrets were generated without printing them.")
    print("Keep a separate encrypted backup of ENCRYPTION_KEY.")


if __name__ == "__main__":
    main()
