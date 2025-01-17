import openai
import json
import logging
from typing import Dict

class TradeSuggestionManager:
    """
    Uses OpenAI to generate trade suggestions based on strategy JSON, market data, and budget allocation.
    Integrates with TradeManager to store and synchronize trades.
    """

    def __init__(self, openai_api_key, trade_manager):
        self.logger = logging.getLogger(self.__class__.__name__)
        openai.api_key = openai_api_key
        self.trade_manager = trade_manager  # Integration with TradeManager

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
        - RESPOND ONLY with a JSON array of trades that, no other information required.

        Respond with the JSON array of trades.
        """

    def generate_trades(self, strategy_json, market_data, budget):
        """
        Sends strategy JSON, market data, and budget to OpenAI to generate trade suggestions.
        Stores valid trades into TradeManager.
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
            self.logger.debug(f"Raw API response: {response}")

            # Validate response structure
            if "choices" in response and response["choices"]:
                content = response["choices"][0].get("message", {}).get("content", "")
                if not content:
                    self.logger.error("No content in API response.")
                    return []
                try:
                    trades = json.loads(content)
                except json.JSONDecodeError as e:
                    self.logger.error(f"Error decoding JSON from OpenAI response: {e}")
                    return []

                # Validate and store trades
                valid_trades = []
                for trade in trades:
                    if self.validate_trade_format(trade):
                        self.trade_manager.record_trade(trade)
                        valid_trades.append(trade)
                    else:
                        self.logger.warning(f"Invalid trade format: {trade}")

                self.logger.info(f"Generated and validated trades: {valid_trades}")
                return valid_trades
            else:
                self.logger.error("Unexpected API response format: No 'choices' found.")
                return []
        except openai.error.OpenAIError as e:
            self.logger.error(f"OpenAI API error: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Unhandled error generating trades: {e}")
            return []

    def validate_trade_format(self, trade):
        """
        Validates the format of a trade dictionary.
        """
        required_fields = [
            "trade_id", "strategy_name", "asset", "side", "trade_type", "amount", 
            "budget_allocation", "price", "stop_loss", "take_profit", "leverage", "market_type", "status"
        ]
        try:
            for field in required_fields:
                if field not in trade:
                    raise ValueError(f"Missing required field: {field}")
            if trade["trade_type"] not in ["long", "short"]:
                raise ValueError(f"Invalid trade_type: {trade['trade_type']}")
            return True
        except Exception as e:
            self.logger.error(f"Trade validation error: {e}")
            return False

    def revalidate_trades(self, strategy_id: str, market_data: Dict[str, Dict]):
        """
        Revalidates existing trades for a given strategy and suggests updates if needed.
        """
        try:
            active_trades = self.trade_manager.get_active_trades()
            strategy_trades = [trade for trade in active_trades if trade["strategy_name"] == strategy_id]

            for trade in strategy_trades:
                asset_data = market_data.get(trade["asset"])
                if not asset_data:
                    self.logger.warning(f"No market data available for asset {trade['asset']}.")
                    continue

                if not self.validate_trade_against_market(trade, asset_data):
                    self.logger.info(f"Trade {trade['trade_id']} is no longer valid. Suggesting update.")
                    updated_trades = self.generate_trades({"id": strategy_id}, market_data, trade["budget_allocation"])
                    return updated_trades
        except Exception as e:
            self.logger.error(f"Error revalidating trades for strategy '{strategy_id}': {e}")
            return []

    def validate_trade_against_market(self, trade: Dict, market_data: Dict) -> bool:
        """
        Validates an active trade against current market conditions.
        """
        try:
            current_price = market_data.get("current_price")
            stop_loss = float(trade.get("stop_loss", 0))
            take_profit = float(trade.get("take_profit", 0))

            if stop_loss and current_price <= stop_loss:
                return False
            if take_profit and current_price >= take_profit:
                return False
            return True
        except Exception as e:
            self.logger.error(f"Error validating trade against market: {e}")
            return False
