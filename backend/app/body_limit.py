"""Bound requests before the multipart parser can spool files to disk."""
import asyncio

from starlette.responses import JSONResponse


class BodyLimitMiddleware:
    def __init__(self,app,max_bytes=9*1024*1024,timeout_seconds=30):
        self.app,self.max_bytes,self.timeout_seconds = app,max_bytes,timeout_seconds

    async def __call__(self,scope,receive,send):
        if scope["type"]!="http" or scope.get("method") in {"GET","HEAD","OPTIONS"}:
            return await self.app(scope,receive,send)
        length = dict(scope.get("headers", [])).get(b"content-length")
        if length is not None and (len(length) > 20 or not length.isdigit()):
            return await JSONResponse({"detail":"Invalid Content-Length"},status_code=400)(scope,receive,send)
        if length is not None and int(length) > self.max_bytes:
            return await JSONResponse({"detail":"Request body exceeds the 9 MiB limit"},status_code=413)(scope,receive,send)
        # A list of millions of tiny chunks exceeded the nominal byte budget in
        # Python-object overhead. Keep one bounded buffer and a total deadline.
        body = bytearray()
        try:
            async with asyncio.timeout(self.timeout_seconds):
                while True:
                    message = await receive()
                    if message["type"]=="http.disconnect":
                        return
                    chunk = message.get("body",b"")
                    if len(body)+len(chunk)>self.max_bytes:
                        response = JSONResponse({"detail":"Request body exceeds the 9 MiB limit"},status_code=413)
                        return await response(scope,receive,send)
                    body.extend(chunk)
                    if not message.get("more_body",False):
                        break
        except TimeoutError:
            return await JSONResponse({"detail":"Request body timed out"},status_code=408)(scope,receive,send)
        delivered = False
        async def limited_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type":"http.request","body":bytes(body),"more_body":False}
            return await receive()
        await self.app(scope,limited_receive,send)
