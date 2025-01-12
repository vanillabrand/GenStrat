import openai
import json
import logging


class TradeSuggestionManager:
    """
    Uses OpenAI to generate trade suggestions based on strategy JSON and market data.
    """

    def __init__(self, openai_api_key):
        self.logger = logging.getLogger(self.__class__.__name__)
        openai.api_key = openai_api_key

    async def fetch_market_data(self, asset, market_type, exchange):
        """
        Fetches the required market data for an asset.
        :param asset: The trading pair (e.g., BTC/USDT).
        :param market_type: The market type (spot, futures, margin).
        :param exchange: The exchange object for making API calls.
        :return: A dictionary containing market data.
        """
        try:
            ticker = await exchange.fetch_ticker(asset)
            leverage_info = await exchange.fetch_markets()
            leverage_data = next((market for market in leverage_info if market['symbol'] == asset), {})

            market_data = {
                "current_price": ticker["last"],
                "high": ticker["high"],
                "low": ticker["low"],
                "volume": ticker["baseVolume"],
                "leverage": leverage_data.get("leverage", None),  # Max leverage if available
                "market_type": market_type
            }
            self.logger.info(f"Market data fetched for {asset}: {market_data}")
            return market_data
        except Exception as e:
            self.logger.error(f"Failed to fetch market data for {asset}: {e}")
            return {}

    def validate_trade_format(self, trade):
        """
        Validates the format of a trade dictionary.
        """
        required_fields = [
            "trade_id", "strategy_name", "asset", "side", "trade_type", "amount", 
            "price", "stop_loss", "take_profit", "leverage", "market_type", "status"
        ]
        for field in required_fields:
            if field not in trade:
                raise ValueError(f"Missing required field: {field}")
        if trade["trade_type"] not in ["long", "short"]:
            raise ValueError(f"Invalid trade_type: {trade['trade_type']}")

    def create_prompt(self, strategy_json, market_data):
        """
        Creates a detailed prompt for OpenAI to generate trades.
        :param strategy_json: JSON object representing the strategy.
        :param market_data: Market data for the relevant assets.
        :return: A string prompt for OpenAI.
        """
        return f"""
        Based on the following strategy and market data, generate trade suggestions for both long and short positions.
        Ensure the trades include all parameters needed for execution and are optimized for the current and future market conditions.

        ### Strategy JSON:
        {json.dumps(strategy_json, indent=2)}

        ### Market Data:
        {json.dumps(market_data, indent=2)}

        ### Required Trade Format:
        Each trade must include:
        - `trade_id`: A unique identifier.
        - `strategy_name`: The name of the strategy.
        - `asset`: The trading pair (e.g., BTC/USDT).
        - `side`: Either 'buy' or 'sell'.
        - `trade_type`: Either 'long' or 'short' to specify the trade direction.
        - `amount`: The size of the position.
        - `price`: The target price for entry.
        - `stop_loss`: Stop-loss price based on the strategy's risk management.
        - `take_profit`: Take-profit price based on the strategy's reward target.
        - `leverage`: Leverage amount (if applicable).
        - `market_type`: Spot, futures, or margin.
        - `status`: Initially set to 'pending'.

        ### Instructions:
        - Include both long and short trades where applicable.
        - Ensure the side (`buy` or `sell`) aligns with the trade type (`long` or `short`).
        - Factor in future market conditions to optimize stop-loss and take-profit levels.
        - Validate risk/reward parameters using the stop_loss and take_profit fields.
        - Optimize the position size and amount based on market conditions and available funds.
        - Respond only in JSON format, strictly adhering to the structure above.

        Respond with the JSON array of trades.
        """

    def generate_trades(self, strategy_json, market_data):
        """
        Sends strategy JSON and market data to OpenAI to generate trade suggestions.
        :param strategy_json: JSON object representing the strategy.
        :param market_data: Market data for the relevant assets.
        :return: List of validated trade dictionaries.
        """
        try:
            prompt = self.create_prompt(strategy_json, market_data)
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "system", "content": "You are an expert trading assistant."},
                          {"role": "user", "content": prompt}]
            )
            trades = json.loads(response.choices[0].message.content)

            # Validate trade format
            for trade in trades:
                self.validate_trade_format(trade)

            self.logger.info(f"Generated trades: {trades}")
            return trades
        except Exception as e:
            self.logger.error(f"Error generating trades: {e}")
            return []
