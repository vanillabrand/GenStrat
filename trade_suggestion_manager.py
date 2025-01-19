import openai
import json
import logging
from typing import Dict, List


class TradeSuggestionManager:
    """
    Uses OpenAI to generate trade suggestions based on strategy JSON, market data, and budget allocation.
    Integrates with TradeManager to store and synchronize trades.
    """

    def __init__(self, openai_api_key, trade_manager):
        self.logger = logging.getLogger(self.__class__.__name__)
        openai.api_key = openai_api_key
        self.trade_manager = trade_manager  # Integration with TradeManager

    async def fetch_market_data(self, assets: List[str], market_type: str, exchange) -> Dict[str, Dict]:
        """
        Fetches market data for multiple assets.
        """
        market_data = {}
        try:
            for asset in assets:
                try:
                    ticker = await exchange.fetch_ticker(asset)
                    leverage_info = await exchange.fetch_markets()
                    leverage_data = next((market for market in leverage_info if market['symbol'] == asset), {})
                    
                    market_data[asset] = {
                        "current_price": ticker["last"],
                        "high": ticker["high"],
                        "low": ticker["low"],
                        "volume": ticker["baseVolume"],
                        "leverage": leverage_data.get("leverage", None),  # Max leverage if available
                        "market_type": market_type,
                    }
                except Exception as asset_error:
                    self.logger.warning(f"Failed to fetch market data for {asset}: {asset_error}")
                    market_data[asset] = {}  # Ensure asset has an entry even if data is missing

            self.logger.info(f"Fetched market data for assets: {market_data.keys()}")
            return market_data
        except Exception as e:
            self.logger.error(f"Failed to fetch market data: {e}")
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
        - `price`: The target entry price based on the strategy. If not applicable, set to 0.
        - `stop_loss`: Stop-loss price as per strategy risk management. If not applicable, set to 0.
        - `take_profit`: Take-profit price as per strategy reward target. If not applicable, set to 0.
        - `leverage`: Leverage amount (if applicable). Be aware of the leverage limits on Bitget.
        - `market_type`: Spot, futures, or margin.
        - `status`: Initially set to 'pending'.
        - `order_type`: Market, limit, stop, stop-limit.

        ### Instructions:
        - Allocate portions of the total budget across trades.
        - Ensure budget allocations are reasonable and do not exceed the total budget.
        - Respond only with a JSON array of trades.
        """

    def generate_trades(self, strategy_json, market_data, budget):
        """
        Generates and validates trades, ensuring they align with exchange requirements before storing.
        """
        try:
            prompt = self.create_prompt(strategy_json, market_data, budget)
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an expert trading assistant."},
                    {"role": "user", "content": prompt}
                ]
            )
            self.logger.debug(f"Raw OpenAI response: {response}")

            content = response["choices"][0]["message"]["content"]
            trades = json.loads(content)
            valid_trades = []

            for trade in trades:
                processed_trade = self.process_trade_for_storage(trade, market_data)
                if processed_trade and self.validate_trade_format(processed_trade):
                    self.trade_manager.record_trade(processed_trade)
                    valid_trades.append(processed_trade)
                else:
                    self.logger.warning(f"Invalid or unprocessable trade: {trade}")

            self.logger.info(f"Generated and validated trades: {valid_trades}")
            return valid_trades
        except Exception as e:
            self.logger.error(f"Error generating trades: {e}")
            return []

    def validate_trade_format(self, trade):
        """
        Validates the format of a trade dictionary based on its order type and other contextual parameters.
        """
        required_fields = [
            "trade_id", "strategy_name", "asset", "side", "trade_type", "order_type",
            "amount", "budget_allocation", "market_type", "status"
        ]
        numeric_fields = ["amount", "budget_allocation", "stop_loss", "take_profit", "leverage"]

        try:
            for field in required_fields:
                if field not in trade:
                    raise ValueError(f"Missing required field: {field}")

            # Validate numeric fields
            for field in numeric_fields:
                if field in trade and not isinstance(trade[field], (int, float)):
                    raise ValueError(f"Invalid value for {field}: {trade[field]}")

            return True
        except Exception as e:
            self.logger.error(f"Trade validation error: {e}")
            return False

    def process_trade_for_storage(self, trade, market_data):
        """
        Cleans and processes a trade for storage based on its order type and market data.
        """
        try:
            order_type = trade.get("order_type", "market")
            if order_type in ["market", "limit", "stop", "stop-limit"]:
                trade["price"] = trade.get("price") or market_data.get(trade["asset"], {}).get("current_price", 0)
            if "stop_price" in trade and order_type in ["stop", "stop-limit"]:
                if not trade.get("stop_price"):
                    raise ValueError(f"Missing stop_price for order: {trade}")

            return trade
        except Exception as e:
            self.logger.error(f"Error processing trade: {e}")
            return None
