import openai
import json
import logging


class TradeSuggestionManager:
    """
    Uses OpenAI to generate trade suggestions based on strategy JSON, market data, and budget allocation.
    """

    def __init__(self, openai_api_key):
        self.logger = logging.getLogger(self.__class__.__name__)
        openai.api_key = openai_api_key

    async def fetch_market_data(self, asset, market_type, exchange):
        """
        Fetches the required market data for an asset.
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

    def create_prompt(self, strategy_json, market_data, budget):
        """
        Creates a detailed prompt for OpenAI to generate trades, including budget allocation.
        """
        return f"""
        Based on the following strategy, market data, and total budget, generate trade suggestions.
        Allocate the budget across trades and include the allocated amount for each trade.

        ### Strategy JSON:
        {json.dumps(strategy_json, indent=2)}

        ### Market Data:
        {json.dumps(market_data, indent=2)}

        ### Budget:
        {budget}

        ### Required Trade Format:
        Each trade must include:
        - `trade_id`: A unique identifier.
        - `strategy_name`: The name of the strategy.
        - `asset`: The trading pair (e.g., BTC/USDT).
        - `side`: Either 'buy' or 'sell'.
        - `trade_type`: Either 'long' or 'short'.
        - `amount`: The position size.
        - `budget_allocation`: The portion of the budget allocated to this trade.
        - `price`: The target entry price.
        - `stop_loss`: Stop-loss price as per strategy risk management.
        - `take_profit`: Take-profit price as per strategy reward target.
        - `leverage`: Leverage amount (if applicable).
        - `market_type`: Spot, futures, or margin.
        - `status`: Initially set to 'pending'.

        ### Instructions:
        - Allocate portions of the total budget across trades.
        - Ensure budget allocations are reasonable and do not exceed the total budget.
        - Respond only in JSON format, strictly adhering to the structure above.

        Respond with the JSON array of trades.
        """
    def generate_trades(self, strategy_json, market_data, budget):
        """
        Sends strategy JSON, market data, and budget to OpenAI to generate trade suggestions.
        """


        try:
            prompt = self.create_prompt(strategy_json, market_data, budget)
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "system", "content": "You are an expert trading assistant."},
                          {"role": "user", "content": prompt}]
            )
            trades = json.loads(response.choices[0].message["content"])


            
      
            self.logger.info(f"Generated trades: {trades}")
            return trades
        except Exception as e:
            self.logger.error(f"Error generating trades: {e}")
            return []


    def validate_trade_format(self, trade):
        """
        Validates the format of a trade dictionary.
        """
        required_fields = [
            "trade_id", "strategy_name", "asset", "side", "trade_type", "amount", 
            "budget_allocation", "price", "stop_loss", "take_profit", "leverage", "market_type", "status"
        ]
        for field in required_fields:
            if field not in trade:
                raise ValueError(f"Missing required field: {field}")
        if trade["trade_type"] not in ["long", "short"]:
            raise ValueError(f"Invalid trade_type: {trade['trade_type']}")
