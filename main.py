import ccxt
from user_interface import UserInterface

def main():
    # Initialize the exchange object (e.g., Bitget)
    exchange = ccxt.bitget({
        "apiKey": os.env.get("BITGET_API_KEY"),
        "secret": os.env.get("BITGET_API_SECRET"),
        "password": os.env.get("BITGET_API_PASSPHRASE")  # If applicable
    })
    
    # Pass the exchange to UserInterface
    ui = UserInterface(exchange)
    ui.main()

if __name__ == "__main__":
    main()
