"""Read-only startup checks against an explicitly selected app origin. No signups/scans."""
import argparse
import json
import urllib.request
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', default='http://localhost:3000')
    parser.add_argument('--web-only', action='store_true', help='Do not require a worker heartbeat during staged web-only startup')
    args = parser.parse_args()
    url = urlsplit(args.origin)
    if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in {'', '/'}:
        parser.error('Use an exact HTTP(S) origin without credentials or path')
    results = {}
    paths = ['/', '/api/health'] if args.web_only else ['/', '/api/health', '/api/ready']
    for path in paths:
        with urllib.request.urlopen(args.origin.rstrip('/') + path, timeout=10) as response:
            assert response.status == 200
            if path.startswith('/api/'):
                result = json.load(response)
                assert result['status'] in {'ok', 'ready'}
            else:
                assert b'InternPilot' in response.read()
            results[path] = 'passed'
    print(json.dumps({'checks': results, 'scope': 'web/API/database readiness only; check each worker role separately in Automation'}))


if __name__ == '__main__':
    main()
