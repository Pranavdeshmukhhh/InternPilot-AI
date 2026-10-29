"""Verify the selected public preview over TLS without disabling certificate checks.

This checks HTTP responses and published asset provenance, not browser behavior.
Run with the managed environment's normal trusted CA/proxy configuration.
"""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = set()
        self.workspace_links = []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        path = (
            attrs.get("src", "")
            if tag == "script"
            else attrs.get("href", "")
            if tag == "link"
            else ""
        )
        if path.startswith("/_next/static/") and path.endswith((".js", ".css")):
            self.paths.add(path)
        if tag == "a" and attrs.get("href") == "/register":
            self.workspace_links.append(attrs["href"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--export",
        type=Path,
        help="Compare published assets to this exact static output",
    )
    args = parser.parse_args()
    url = urlsplit(args.origin)
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
    ):
        parser.error("Use the exact selected HTTPS origin")
    origin = args.origin.rstrip("/")
    report = {
        "at": datetime.now(UTC).isoformat(),
        "url": origin,
        "tls_verified": True,
        "browser_test": False,
        "checks": {},
        "asset_checks": {},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.get(origin)
            assert response.status_code == 200
            assert response.url.host == url.hostname, "Unexpected off-site redirect"
            assert (
                "Less searching." in response.text
                and "fictional examples" in response.text
            )
            assert origin + "/social-preview.png" in response.text
            page = Assets()
            page.feed(response.text)
            assert not page.workspace_links
            report.update(
                public_response=response.status_code,
                no_public_registration=True,
                absolute_social_url=True,
            )
            for path, content_type in [
                ("/demo", "text/html"),
                ("/login", "text/html"),
                ("/privacy", "text/html"),
                ("/terms", "text/html"),
                ("/contact", "text/html"),
                ("/icon.svg", "image/svg+xml"),
                ("/apple-icon.png", "image/png"),
                ("/social-preview.png", "image/png"),
                ("/third-party-notices.txt", "text/plain"),
            ]:
                item = client.get(origin + path)
                assert item.status_code == 200, path
                assert item.headers.get("content-type", "").startswith(content_type), (
                    path
                )
                report["checks"][path] = {
                    "status": item.status_code,
                    "type": item.headers.get("content-type"),
                }
            assert page.paths, "No page assets found"
            for path in sorted(page.paths):
                item = client.get(origin + path)
                assert item.status_code == 200, path
                checksum = hashlib.sha256(item.content).hexdigest()
                matched = None
                if args.export:
                    local = (
                        args.export.resolve() / unquote(path).lstrip("/")
                    ).resolve()
                    assert (
                        local.is_relative_to(args.export.resolve()) and local.is_file()
                    )
                    assert checksum == hashlib.sha256(local.read_bytes()).hexdigest(), (
                        path
                    )
                    matched = True
                report["asset_checks"][path] = {
                    "status": item.status_code,
                    "sha256": checksum,
                    "matches_export": matched,
                }
            report["passed"] = True
        print(json.dumps(report, indent=2))
    finally:
        args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
