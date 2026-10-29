"""Build a reviewed source-only archive from tracked files; no runtime/history bundle."""
import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def allowed(name):
    p = Path(name)
    if any(x in {'.git', '.venv', 'node_modules', 'data', 'backups', 'exports', 'private', '.secrets', '__pycache__'} or x.startswith('.next') for x in p.parts):
        return False
    if p.suffix.lower() in {'.db', '.sqlite', '.sqlite3', '.p12', '.pfx', '.key', '.pem', '.zip', '.log', '.pyc', '.dump', '.bak'} or p.name.startswith('.env') and p.name != '.env.example':
        return False
    if name.startswith('artifacts/'):
        if name in {'artifacts/founder/backend.json','artifacts/founder/backend.xml','artifacts/founder/security.json',
                    'artifacts/founder/migrations.json','artifacts/founder/hosting.json','artifacts/founder/configuration.json',
                    'artifacts/founder/github-history.json','artifacts/founder/local-history.json','artifacts/founder/secret-triage.json',
                    'artifacts/founder/ui/report.json','artifacts/founder/ui/overview-desktop.png','artifacts/founder/ui/overview-mobile.png'}:
            return True
        return name.startswith('artifacts/phase7-ui/') and p.name != 'failure.png' or name in {
            'artifacts/phase7-performance-summary.json', 'artifacts/phase7-final-backend.json', 'artifacts/phase7-recovery.json', 'artifacts/phase7-dependencies.json', 'artifacts/phase8-clean-backend.xml', 'artifacts/phase8-clean-backend.json', 'artifacts/phase8-compose.json', 'artifacts/phase8-license-inventory.json', 'artifacts/phase8-clean-ui/report.json',
            'artifacts/phase9-backend.xml', 'artifacts/phase9-backend.json', 'artifacts/phase9-compose.json',
            'artifacts/phase9-public/report.json', 'artifacts/phase9-public/lighthouse-uncompressed-v1.json',
            'artifacts/phase9-static/report.json', 'artifacts/phase9-static/lighthouse-mobile.json',
            'artifacts/phase9-static/desktop.png', 'artifacts/phase9-static/mobile.png', 'artifacts/phase9-static/demo-mobile.png',
            'artifacts/phase9-live/http.json', 'artifacts/phase9-live/deployment.json',
            'artifacts/phase9-workspace/report.json', 'artifacts/phase9-workspace/explorer-desktop.png',
            'artifacts/access-update/backend.json', 'artifacts/access-update/backend.xml',
            'artifacts/access-update/ui/report.json', 'artifacts/access-update/ui/terms-desktop.png',
            'artifacts/access-update/ui/terms-mobile.png', 'artifacts/access-update/ui/login-desktop.png',
            'artifacts/access-update/configuration.json', 'artifacts/access-update/deployment.json',
            'artifacts/access-update/live-http.json', 'artifacts/access-update/static/report.json',
        }
    return name in {'README.md', 'compose.yaml', '.env.example', '.gitignore', '.gitattributes', '.gitleaksignore', '.dockerignore', 'render.yaml', 'LICENSE', 'THIRD_PARTY_NOTICES.md'} or name.startswith(('backend/', 'frontend/', 'scripts/', 'docs/', 'deploy/', '.github/'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=ROOT / 'artifacts/phase8-package.json')
    arguments = parser.parse_args()
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    names = sorted(n for n in names if n and allowed(n) and (ROOT / n).is_file() and (ROOT / n).resolve().is_relative_to(ROOT) and (ROOT / n).resolve().relative_to(ROOT).as_posix() == n)
    required = {'frontend/scripts/check-contract.mjs', 'frontend/tests/query-runtime.test.mjs', 'frontend/openapi.json', 'backend/tests/fixtures/schema_v1_postgresql.sql', 'backend/requirements-audit.txt'}
    if not required.issubset(names):
        raise RuntimeError('Release is missing executable contracts/tests/migration fixtures')
    forbidden = re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|(?:ghp_|github_pat_)[A-Za-z0-9_]{30,}')
    checksums = {}
    for name in names:
        content = (ROOT / name).read_bytes()
        if forbidden.search(content):
            raise RuntimeError('Potential private credential in release path: ' + name)
        checksums[name] = hashlib.sha256(content).hexdigest()
    target = ROOT / 'dist/InternPilot-AI-release.zip'
    target.parent.mkdir(exist_ok=True)
    temporary = target.with_suffix('.tmp.zip')
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.write(ROOT / name, 'InternPilot-AI/' + name)
        archive.writestr('InternPilot-AI/RELEASE_MANIFEST.json', json.dumps(checksums, indent=2))
    with zipfile.ZipFile(temporary) as archive:
        assert archive.testzip() is None
        for name, checksum in checksums.items():
            assert hashlib.sha256(archive.read('InternPilot-AI/' + name)).hexdigest() == checksum
    temporary.replace(target)
    report = {'files': len(names), 'bytes': target.stat().st_size, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'manifest_verified': True, 'scan': 'allowlist plus private-key/GitHub-token signatures; not exhaustive historical secret scanning', 'license': 'owner license choice pending; see THIRD_PARTY_NOTICES.md'}
    target.with_suffix('.zip.sha256').write_text(report['sha256'] + '  ' + target.name + '\n')
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
