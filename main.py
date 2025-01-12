import ccxt
from user_interface import UserInterface
import os
import asyncio
import logging

async def async_main():
    # Initialize the exchange object (e.g., Bitget)
    exchange = ccxt.bitget({
        "apiKey": os.getenv("BITGET_API_KEY"),
        "secret": os.getenv("BITGET_API_SECRET"),
        "password": os.getenv("BITGET_API_PASSPHRASE")  # If applicable
    })

    LOGGING_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    LOGGING_FILE = 'trading_bot.log'
    LOGGING_LEVEL = logging.DEBUG

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.FileHandler('trading_bot.log'),
            logging.StreamHandler()
        ]
    )
   
    # Pass the exchange to UserInterface
    ui = UserInterface(exchange, logging)
    await ui.main()  # Await the main loop of UserInterface

def main():
    # Check if there's an existing running event loop
    try:
        asyncio.run(async_main())  # Try to start the async_main coroutine
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            # Handle nested loops by creating tasks instead
            loop = asyncio.get_event_loop()
            loop.create_task(async_main())
            loop.run_forever()

if __name__ == "__main__":
    main()
