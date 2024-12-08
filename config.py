# config.py

import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Load environment variables
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
BITGET_API_KEY = os.getenv('BITGET_API_KEY')
BITGET_SECRET = os.getenv('BITGET_SECRET')
BITGET_PASSWORD = os.getenv('BITGET_PASSWORD')
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB = int(os.getenv('REDIS_DB', 0))
HUGGINGFACE_API_KEY="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"

# Logging configuration
LOGGING_LEVEL = logging.INFO  # Change to logging.DEBUG for more detailed logs
LOGGING_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
LOGGING_FILE = 'trading_bot.log'

logging.basicConfig(
    level=LOGGING_LEVEL,
    format=LOGGING_FORMAT,  
    handlers=[
        logging.FileHandler(LOGGING_FILE),
        logging.StreamHandler()
    ]
)
