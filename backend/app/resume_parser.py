"""Short-lived parser child. No application configuration or secrets imported.

POSIX resource limits are defense in depth, not a filesystem/network sandbox.
The controller also enforces wall time and concurrency on every platform.
"""
import json
import sys


def main():
    if sys.platform != "win32":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
        resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    from .documents import MAX_UPLOAD_BYTES, parse_resume
    try:
        content = sys.stdin.buffer.read(MAX_UPLOAD_BYTES + 1)
        result = parse_resume(content, sys.argv[1])
        sys.stdout.write(json.dumps({"result": result}, ensure_ascii=True))
    except (ValueError, MemoryError):
        # Parser input must never become a traceback, log or executable argument.
        sys.stdout.write(json.dumps({"error": "Could not safely parse this resume. Use a readable PDF, DOCX or UTF-8 TXT within the documented limits."}))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
