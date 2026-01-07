## config/logger.py

import logging
import os
from config.settings import config

def setup_logging():
    
    os.makedirs("log", exist_ok=True)
    
    handlers = [
        logging.FileHandler("log/bot.log"),
        logging.StreamHandler()
    ]

    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format="%(asctime)s [%(levelname)s] %(message)s",  
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers
    )