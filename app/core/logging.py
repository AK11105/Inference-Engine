import logging
import json
from datetime import datetime
from typing import Any, Dict 

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_record: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        
        if hasattr(record, "extra"):
            log_record.update(record.extra)
        
        return json.dumps(log_record)
    
def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers = [handler]