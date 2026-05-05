## config/logger.py

import logging
import json
import os
from logging.handlers import RotatingFileHandler
from config.settings import config


class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter for production"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging() -> None:
    os.makedirs("logs", exist_ok=True)
    
    log_level = getattr(logging, config.LOG_LEVEL, logging.INFO)
    
    # Rotating file handler — max 10MB, keep 5 backups
    file_handler = RotatingFileHandler(
        "logs/bot.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    
    stream_handler = logging.StreamHandler()
    
    # Use JSON format in production, human-readable in dev
    if config.ENVIRONMENT != "DEV":
        formatter = JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)
    
    logging.basicConfig(
        level=log_level,
        handlers=[file_handler, stream_handler],
    )