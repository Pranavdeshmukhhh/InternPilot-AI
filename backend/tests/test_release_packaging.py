"""Release boundary checks; no personal files or archives opened."""
import importlib.util
from pathlib import Path


def test_release_excludes_private_runtime_and_includes_required_contracts():
    path = Path(__file__).parents[2] / 'scripts/release.py'
    spec = importlib.util.spec_from_file_location('release_boundary', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ['.env', 'backend/.env', 'backend/data/profile.json', 'frontend/node_modules/a.js', 'backend/local.db', 'artifacts/dashboard-desktop.png', 'MANIFEST.sha256', 'backups/archive.zip', 'artifacts/phase9-live/credentials.json', 'artifacts/phase9-workspace/profile-mobile.png']:
        assert not module.allowed(name), name
    for name in ['frontend/openapi.json', 'frontend/scripts/check-contract.mjs', 'frontend/tests/query-runtime.test.mjs', 'backend/tests/fixtures/schema_v1_postgresql.sql', 'THIRD_PARTY_NOTICES.md', 'artifacts/phase7-ui/explorer-light.png', 'frontend/public/icon.svg', 'artifacts/phase9-static/mobile.png', 'artifacts/phase9-live/http.json']:
        assert module.allowed(name), name
