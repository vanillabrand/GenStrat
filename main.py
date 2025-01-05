import ccxt
from user_interface import UserInterface
import os
import asyncio

async def async_main():
    # Initialize the exchange object (e.g., Bitget)
    exchange = ccxt.bitget({
        "apiKey": os.getenv("BITGET_API_KEY"),
        "secret": os.getenv("BITGET_API_SECRET"),
        "password": os.getenv("BITGET_API_PASSPHRASE")  # If applicable
    })

    # Pass the exchange to UserInterface
    ui = UserInterface(exchange)
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
