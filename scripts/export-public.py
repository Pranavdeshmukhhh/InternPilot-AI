"""Build only shared public pages for static hosting; never export private app/data.

Destination must be a separate disposable project directory, not the repository.
Requires the already installed matching frontend dependencies and Node toolchain.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--destination", type=Path, required=True)
    p.add_argument("--origin", required=True)
    args = p.parse_args()
    origin = urlsplit(args.origin)
    if (
        origin.scheme != "https"
        or not origin.hostname
        or origin.username
        or origin.password
        or origin.path not in {"", "/"}
        or origin.query
        or origin.fragment
    ):
        p.error("Use the actual HTTPS site origin")
    target = args.destination.resolve()
    if target == ROOT or ROOT in target.parents:
        p.error("Use a separate site directory")
    target.mkdir(parents=True, exist_ok=True)
    # Only generated public source is replaced; hosting identity remains untouched.
    if (target / "src").exists():
        shutil.rmtree(target / "src")
    for rel in [
        "src/features/public",
        "src/components/theme-toggle.tsx",
        "src/features/workspace/performance.tsx",
        "src/styles/tokens.css",
        "src/app/layout.tsx",
        "src/app/globals.css",
        "src/app/page.tsx",
        "src/app/demo",
        "src/app/privacy",
        "src/app/terms",
        "src/app/contact",
        "src/app/social-image",
        "src/app/robots.ts",
        "public",
        "package.json",
        "scripts/generate-notices.mjs",
        "package-lock.json",
        "postcss.config.mjs",
        "tailwind.config.ts",
        "tsconfig.json",
        "next-env.d.ts",
    ]:
        src = ROOT / "frontend" / rel
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
        else:
            shutil.copyfile(src, dest)
    (target / "next.config.mjs").write_text(
        "export default {output:'export',images:{unoptimized:true},poweredByHeader:false};\n"
    )
    # This host has no account API: a truthful access page, never a credential form.
    login = target / "src/app/login"
    login.mkdir(parents=True, exist_ok=True)
    (login / "page.tsx").write_text("export {default} from '@/features/public/access';\nexport const metadata={title:'Workspace sign-in',robots:{index:false,follow:false}};\n")
    (target / ".gitignore").write_text(
        "node_modules/\n.next/\nout/\n*.tsbuildinfo\n.env*\n"
    )
    dependencies = target / "node_modules"
    if not dependencies.exists():
        dependencies.symlink_to(
            ROOT / "frontend/node_modules", target_is_directory=True
        )
    env = dict(
        os.environ,
        PUBLIC_SITE_URL=args.origin,
        PUBLIC_DEMO_ONLY="true",
        NEXT_TELEMETRY_DISABLED="1",
    )
    subprocess.run(["npm", "run", "build"], cwd=target, env=env, check=True)
    assert (target / "out/index.html").exists() and (target / "out/demo.html").exists()
    for private in [
        "register.html",
        "overview.html",
        "applications.html",
    ]:
        assert not (target / "out" / private).exists()
    print(
        json.dumps(
            {
                "public_only": True,
                "output": str(target / "out"),
                "private_routes_exported": False,
            }
        )
    )


if __name__ == "__main__":
    main()
