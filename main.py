import ccxt
from user_interface import UserInterface
import os
import asyncio
import logging


async def async_main():

    # Logging configuration
    LOGGING_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    LOGGING_FILE = 'trading_bot.log'

    logging.basicConfig(
        level=logging.DEBUG,
        format=LOGGING_FORMAT,
        handlers=[
            logging.FileHandler(LOGGING_FILE),
            logging.StreamHandler()
        ]
    )
    
    try:
        # Initialize the exchange object (e.g., Bitget)
        exchange = ccxt.bitget({
            "apiKey": os.getenv("BITGET_API_KEY"),
            "secret": os.getenv("BITGET_API_SECRET"),
            "password": os.getenv("BITGET_API_PASSPHRASE"),
            "enableRateLimit": True
            
        })
        
       # exchange.load_markets()  # Pre-load market data to avoid runtime delays
      
    except Exception as e:
        logging.error(f"Failed to initialize exchange: {e}")
        return

    

    # Pass the exchange to UserInterface and launch the app
    try:
        ui = UserInterface(exchange, logging)
        await ui.main()
    except Exception as e:
        logging.error(f"Application error: {e}")
    finally:
        logging.info("Shutting down application.")


def main():
    try:
        asyncio.run(async_main())  # Launch the application
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            loop = asyncio.get_event_loop()
            loop.run_until_complete(async_main())


if __name__ == "__main__":
    main()
