"""Bound requests before the multipart parser can spool files to disk."""
from starlette.responses import JSONResponse


class BodyLimitMiddleware:
    def __init__(self,app,max_bytes=9*1024*1024):
        self.app,self.max_bytes = app,max_bytes

    async def __call__(self,scope,receive,send):
        if scope["type"]!="http" or scope.get("method") in {"GET","HEAD","OPTIONS"}:
            return await self.app(scope,receive,send)
        size, chunks = 0, []
        while True:
            message = await receive()
            if message["type"]=="http.disconnect":
                return
            chunk = message.get("body",b"")
            size += len(chunk)
            if size>self.max_bytes:
                response = JSONResponse({"detail":"Request body exceeds the 9 MiB limit"},status_code=413)
                return await response(scope,receive,send)
            chunks.append(chunk)
            if not message.get("more_body",False):
                break
        delivered = False
        async def limited_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type":"http.request","body":b"".join(chunks),"more_body":False}
            return await receive()
        await self.app(scope,limited_receive,send)
