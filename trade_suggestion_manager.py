import json
import logging
from typing import Dict, List
import openai
import asyncio


class TradeSuggestionManager:
    """
    Manages trade suggestions using OpenAI and market data.
    Integrates with TradeManager, MarketMonitor, and TradeMonitor to manage trades dynamically.
    """

    def __init__(self, openai_api_key, trade_manager, strategy_manager, exchange, market_monitor):
        self.logger = logging.getLogger(self.__class__.__name__)
        openai.api_key = openai_api_key
        self.trade_manager = trade_manager
        self.strategy_manager = strategy_manager
        self.exchange = exchange
        self.market_monitor = market_monitor

    async def fetch_market_data(self, assets: List[str]) -> Dict[str, Dict]:
        """
        Fetches market data for multiple assets efficiently.
        Handles async/sync differences based on the exchange's implementation.
        """
        try:
            self.logger.info(f"Fetching market data for assets: {assets}")
            if asyncio.iscoroutinefunction(self.exchange.fetch_tickers):
                market_data = await self.exchange.fetch_tickers(assets)
            else:
                market_data = self.exchange.fetch_tickers(assets)  # Call directly if synchronous

            self.logger.info(f"Market data fetched: {market_data}")
            return market_data
        except Exception as e:
            self.logger.error(f"Failed to fetch market data: {e}", exc_info=True)
            return {}

    async def process_strategy_trades(self, strategy_id: str, budget: float):
        """
        Processes trades for a strategy:
        1. Loads the strategy.
        2. Fetches market data for assets in the strategy.
        3. Generates trades via OpenAI based on market data and strategy.
        4. Monitors generated trades via MarketMonitor.
        """
        try:
            # Step 1: Load the strategy
            strategy = await self.strategy_manager.load_strategy(strategy_id)
            if not strategy:
                raise ValueError(f"Strategy with ID {strategy_id} not found.")
            self.logger.info(f"Loaded strategy {strategy_id}: {strategy['title']}")

            # Step 2: Fetch market data for all asset pairs
            asset_pairs = strategy["data"]["assets"]
            market_data = await self.fetch_market_data(asset_pairs)
            if not market_data:
                self.logger.error(f"Market data could not be fetched for strategy {strategy_id}.")
                return

            # Step 3: Generate trades using OpenAI
            trades = await self.generate_trades(strategy_id, strategy, market_data, budget)
            if not trades:
                self.logger.warning(f"No trades generated for strategy {strategy_id}.")
                return

            # Step 4: Store trades and initiate monitoring
            self.logger.info(f"Generated trades for strategy {strategy_id}: {trades}")
            await self.market_monitor.monitor_strategy(strategy, trades)

        except Exception as e:
            self.logger.error(f"Error processing trades for strategy {strategy_id}: {e}", exc_info=True)

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
        - `strategy_name`: The title of the strategy.
        - `strategy_id`: The unique identifier of the strategy.
        - `asset`: The trading pair (e.g., BTC/USDT).
        - `side`: Either 'buy' or 'sell'.
        - `trade_type`: Either 'long' or 'short'.
        - `amount`: The position size.
        - `budget_allocation`: The portion of the budget allocated to this trade.
        - `price`: The target entry price based on the strategy.
        - `stop_loss`: Stop-loss price as per strategy risk management.
        - `take_profit`: Take-profit price as per strategy reward target.
        - `leverage`: Leverage amount (if applicable).
        - `market_type`: Spot, futures, or margin.
        - `status`: Initially set to 'pending'.
        - `order_type`: Market, limit, stop, stop-limit.

        ### Instructions:
        - Allocate portions of the total budget across trades intelligently based on the strategy.
        - Ensure budget allocations are reasonable and do not exceed the total budget.
        - Respond only with a JSON array of trades. Do NOT include any other information or text in the response.
        """

    async def generate_trades(self, strategy_id, strategy_json, market_data, budget):
        """
        Generates and validates trades using OpenAI.
        """
        try:
            prompt = self.create_prompt(strategy_json, market_data, budget)
            response = await openai.ChatCompletion.acreate(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an expert CRYPTO trading assistant."},
                    {"role": "user", "content": prompt}
                ]
            )

            content = response["choices"][0]["message"]["content"]
            self.logger.info(f"[OpenAI] Response: {content}")

            trades = json.loads(content)
            return self.validate_trades(trades, budget)

        except Exception as e:
            self.logger.error(f"Error generating trades: {e}")
            return []

    def validate_trades(self, trades, budget):
        """
        Validates the generated trades to ensure they are correctly formatted and within the budget.
        """
        try:
            total_allocated = sum(trade["budget_allocation"] for trade in trades)
            if total_allocated > budget:
                raise ValueError(f"Total budget allocation exceeds the total budget: {total_allocated} > {budget}")
            return trades
        except Exception as e:
            self.logger.error(f"Error validating trades: {e}")
            raise