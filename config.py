import os
import logging
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

class Config:
    """
    Centralized configuration management for the application.
    """

    # Redis Configuration
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB = int(os.getenv("REDIS_DB", 0))

    # Exchange API Keys
    BITGET_API_KEY = os.getenv("BITGET_API_KEY")
    BITGET_API_SECRET = os.getenv("BITGET_API_SECRET")
    BITGET_API_PASSPHRASE = os.getenv("BITGET_API_PASSPHRASE")

    # OpenAI API Key
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    # Logging Configuration
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
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

    # Default Parameters
    DEFAULT_BUDGET = float(os.getenv("DEFAULT_BUDGET", 1000.0))
    DEFAULT_MARKET_TYPE = os.getenv("DEFAULT_MARKET_TYPE", "spot")

    @classmethod
    def validate(cls):
        """
        Validate required configuration values are set.
        Raises:
            ValueError: If a required configuration is missing.
        """
        required_keys = [
            "BITGET_API_KEY",
            "BITGET_API_SECRET",
            "BITGET_API_PASSPHRASE",
            "OPENAI_API_KEY"
        ]
        for key in required_keys:
            if not getattr(cls, key):
                raise ValueError(f"Missing required configuration: {key}")

# Validate the configuration on import
Config.validate()
