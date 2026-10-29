"""Install the pinned Linux CI scanner into a chosen directory, with checksum verification."""

import argparse
import hashlib
import io
from pathlib import Path
import tarfile
from urllib.request import urlopen

VERSION = "8.24.3"
SHA256 = "9991e0b2903da4c8f6122b5c3186448b927a5da4deef1fe45271c3793f4ee29c"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    url = f"https://github.com/gitleaks/gitleaks/releases/download/v{VERSION}/gitleaks_{VERSION}_linux_x64.tar.gz"
    with urlopen(url, timeout=60) as response:
        blob = response.read(20 * 1024 * 1024 + 1)
    if hashlib.sha256(blob).hexdigest() != SHA256:
        raise SystemExit("Scanner archive checksum mismatch")
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
        binary = archive.extractfile("gitleaks").read()
    args.directory.mkdir(parents=True, exist_ok=True)
    target = args.directory / "gitleaks"
    target.write_bytes(binary)
    target.chmod(0o700)
    print("Pinned secret scanner installed; archive checksum verified")


if __name__ == "__main__":
    main()
