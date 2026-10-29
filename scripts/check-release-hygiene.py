"""Reject tracked private runtime files without reading or printing their contents."""
from pathlib import PurePosixPath
import subprocess

names=subprocess.check_output(['git','ls-files','-z']).decode().split('\0')
bad=[]
for name in names:
    if not name:continue
    path=PurePosixPath(name)
    if (any(part in {'data','backups','exports','private','.secrets','node_modules','.venv'} for part in path.parts)
            or path.name.startswith('.env') and path.name!='.env.example'
            or path.suffix.lower() in {'.db','.sqlite','.sqlite3','.dump','.bak','.pem','.key','.p12','.pfx'}):
        bad.append(name)
if bad:
    print('Private runtime paths are tracked; remove from the index and investigate history:')
    for path in bad:print(path)
    raise SystemExit(1)
print('Tracked-path hygiene passed. This is not content or Git-history secret scanning.')
