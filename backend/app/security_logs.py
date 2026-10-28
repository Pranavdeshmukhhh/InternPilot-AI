"""OAuth codes and state must never enter HTTP access logs."""
import logging


class OAuthAccessFilter(logging.Filter):
    def filter(self,record):
        if isinstance(record.args,tuple) and len(record.args)>=3:
            args = list(record.args)
            path = args[2]
            if isinstance(path,str) and "/api/outreach/gmail/callback" in path:
                args[2] = path.split("?",1)[0]+"?[redacted]"
                record.args = tuple(args)
        return True


logging.getLogger("uvicorn.access").addFilter(OAuthAccessFilter())
