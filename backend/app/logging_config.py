"""Small structured worker logs without request headers, payloads or secrets."""
import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self,record):
        return json.dumps({"at":datetime.fromtimestamp(record.created,timezone.utc).isoformat(),"level":record.levelname,"logger":record.name,"message":record.getMessage()},ensure_ascii=False)


def configure():
    handler=logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO,handlers=[handler],force=True)
