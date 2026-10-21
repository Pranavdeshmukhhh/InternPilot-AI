"""Package allowlisted source/evidence, excluding secrets and runtime data.

No Git commands or repository credentials are needed. The archive is checked
against its SHA-256 manifest before replacing the previous release artifact.
"""
import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {"README.md","compose.yaml","render.yaml",".env.example",".gitignore",".dockerignore"}
CONFIG_FILES = {
    "backend/Dockerfile","backend/.dockerignore","backend/requirements.txt","backend/requirements.lock",
    "backend/requirements-dev.txt","backend/ruff.toml","backend/pytest.ini",
    "frontend/Dockerfile","frontend/.dockerignore","frontend/package.json","frontend/package-lock.json",
    "frontend/next-env.d.ts","frontend/next.config.mjs","frontend/postcss.config.mjs",
    "frontend/tailwind.config.ts","frontend/tsconfig.json","frontend/eslint.config.mjs",
}
EVIDENCE = {"backend-test-summary.json","backend-tests.xml","documents-tests.xml","frontend-build.json",
    "improvements-backend-tests.xml","ui-acceptance.json","upgrade-postgres.json","upgrade-verification.json",
    "live-discovery.json","live-listings.json","live-rejections.json","offline-replay.json",
    "docker-validation.json","docker-postgres-queue.json","dashboard-desktop.png","dashboard-mobile.png",
    "saved-dark-desktop.png","ui-internpilot-resume.pdf"}
EXCLUDED = {".git","node_modules",".venv","venv","__pycache__",".pytest_cache",".ruff_cache","data","backups"}


def allowed(relative):
    name = relative.as_posix()
    if any(part in EXCLUDED or part.startswith(".next") for part in relative.parts):
        return False
    if name in ROOT_FILES or name in CONFIG_FILES:
        return True
    suffix = relative.suffix.lower()
    if name.startswith(("backend/app/","backend/tests/")):
        return suffix==".py" or name.startswith("backend/app/assets/fonts/") and suffix in {".ttf",".txt"}
    if name.startswith("frontend/src/"):
        return suffix in {".tsx",".ts",".css"}
    if name.startswith("docs/"):
        return suffix in {".md",".json"}
    if name.startswith("scripts/"):
        return suffix in {".py",".ps1",".sh"}
    if name.startswith(".github/workflows/"):
        return suffix in {".yaml",".yml"}
    if name.startswith("deploy/"):
        return suffix==".py" or relative.name=="Dockerfile"
    if relative.parent.as_posix()=="artifacts":
        return relative.name in EVIDENCE
    if relative.parent.as_posix()=="artifacts/docker-local-demo-final":
        return relative.name in {"local-demo-before-submit.png","local-demo-result.json","local-demo-resume.pdf"}
    return False


def main():
    files = sorted(path for path in ROOT.rglob("*") if path.is_file() and not path.is_symlink() and allowed(path.relative_to(ROOT)))
    if not files or not (ROOT/"backend/app/main.py") in files or not (ROOT/"frontend/src/app/page.tsx") in files:
        raise RuntimeError("Required application source is missing")
    checksums = {path.relative_to(ROOT).as_posix():hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    manifest = "".join(f"{checksum}  {name}\n" for name,checksum in checksums.items())
    (ROOT/"MANIFEST.sha256").write_text(manifest,encoding="utf-8")
    target = ROOT/"dist/InternPilot-AI.zip"
    target.parent.mkdir(exist_ok=True)
    temporary = target.with_suffix(".tmp.zip")
    with zipfile.ZipFile(temporary,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in files+[ROOT/"MANIFEST.sha256"]:
            archive.write(path,"InternPilot-AI/"+path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(temporary) as archive:
        assert archive.testzip() is None,"Archive CRC check failed"
        for info in archive.infolist():
            name = PurePosixPath(info.filename)
            assert not name.is_absolute() and ".." not in name.parts
            relative = Path(*name.parts[1:])
            assert relative.as_posix()=="MANIFEST.sha256" or allowed(relative)
        for name,checksum in checksums.items():
            assert hashlib.sha256(archive.read("InternPilot-AI/"+name)).hexdigest()==checksum,name
    temporary.replace(target)
    checksum = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".zip.sha256").write_text(checksum+"  "+target.name+"\n",encoding="utf-8")
    report = {"at":datetime.now(UTC).isoformat(),"archive":target.name,"source_and_evidence_files":len(files),
              "bytes":target.stat().st_size,"sha256":checksum,"crc_and_manifest_verified":True,
              "runtime_data_and_secrets_excluded":True,"git_commands":0}
    (ROOT/"artifacts/package-validation.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    main()
