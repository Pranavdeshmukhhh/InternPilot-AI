"""Bounded, killable resume parsing outside API threads and credentials."""
import asyncio
import json
import os
import sys
import weakref
from pathlib import Path

_POOLS = weakref.WeakKeyDictionary()
PARSER_TIMEOUT_SECONDS = 15


class ParserBusyError(ValueError):
    pass


async def parse_resume_isolated(content, filename):
    from .documents import MAX_UPLOAD_BYTES
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("Resume must contain data and be no larger than 8 MiB.")
    pool = _POOLS.setdefault(asyncio.get_running_loop(), asyncio.Semaphore(2))
    # Only the format suffix crosses argv. User filenames/content stay private.
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".docx", ".txt"}:
        raise ValueError("Supported resume formats: PDF, DOCX, UTF-8 TXT.")
    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "SystemRoot", "WINDIR", "TEMP", "TMP", "LANG") if key in os.environ}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    if pool.locked():
        raise ParserBusyError("Resume parser is busy; retry in a few seconds.")
    async with pool:
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "app.resume_parser", "resume" + suffix,
            cwd=Path(__file__).resolve().parents[1], env=env,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL)
        try:
            output, _ = await asyncio.wait_for(process.communicate(content), PARSER_TIMEOUT_SECONDS)
            if len(output) > 2 * 1024 * 1024:
                raise ValueError("Resume parser output exceeds the safe limit.")
            result = json.loads(output) if output else {}
            if process.returncode or not isinstance(result.get("result"), dict):
                raise ValueError("Could not safely parse this resume. Try a smaller readable document.")
            return result["result"]
        except (asyncio.TimeoutError, json.JSONDecodeError):
            raise ValueError("Resume parsing exceeded its safety budget. Try a smaller readable document.") from None
        finally:
            if process.returncode is None:
                process.kill()
            await process.wait()
