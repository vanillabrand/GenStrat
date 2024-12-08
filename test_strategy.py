import json
import logging
from config import HUGGINGFACE_API_KEY  # Ensure this is correctly set
from strategy_interpreter import StrategyInterpreter  # Replace with your actual module name

if __name__ == "__main__":
    # Initialize the interpreter
    interpreter = StrategyInterpreter(huggingface_api_key=HUGGINGFACE_API_KEY)

    # Example strategy description
    description = """
    Implement a scalping strategy on the BTC/USDT pair using the RSI indicator with a period of 14.
    Enter a long position when RSI falls below 30 and exit when it rises above 70.
    Use a stop loss of 1% and take profit of 2%.
    """

    try:
        strategy = interpreter.interpret(description)
        print("Interpreted Strategy:", json.dumps(strategy, indent=2))
    except ValueError as e:
        print(f"Failed to interpret strategy: {e}")

    # Suggest a new strategy
    try:
        suggested = interpreter.suggest_strategy(risk_level="medium", market_type="spot")
        print("Suggested Strategy:", json.dumps(suggested, indent=2))
    except ValueError as e:
        print(f"Failed to suggest strategy: {e}")
