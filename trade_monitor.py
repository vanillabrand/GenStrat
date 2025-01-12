import asyncio
import logging
from trade_suggestion_manager import TradeSuggestionManager


class TradeMonitor:
    """
    Monitors active trades and validates trade conditions.
    """

    def __init__(self, trade_manager, trade_executor, performance_manager, strategy_manager, risk_manager):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.trade_manager = trade_manager
        self.trade_executor = trade_executor
        self.performance_manager = performance_manager
        self.strategy_manager = strategy_manager
        self.risk_manager = risk_manager
        self.trade_suggestion_manager = TradeSuggestionManager()  # OpenAI integration

    async def monitor_active_trades(self):
        """Main loop to monitor and update active trades."""
        while True:
            try:
                active_trades = self.trade_manager.get_active_trades()
                if not active_trades:
                    self.logger.info("No active trades to monitor.")
                for trade in active_trades:
                    await self.check_trade_conditions(trade)
            except Exception as e:
                self.logger.error(f"Error monitoring trades: {e}")
            await asyncio.sleep(5)

    async def monitor_strategy(self, strategy):
        """
        Monitors entry and exit conditions for a strategy and executes or closes trades accordingly.
        """
        try:
            strategy_data = self.strategy_manager.get_strategy_data(strategy["id"])
            assets = strategy_data.get("assets", [])
            if not assets:
                self.logger.warning(f"Strategy '{strategy['title']}' has no assets to monitor.")
                return

            for asset in assets:
                market_data = await self.fetch_market_data(asset)

                # Generate trades using OpenAI
                suggested_trades = self.trade_suggestion_manager.generate_trades(strategy_data, market_data)
                for trade_details in suggested_trades:
                    if self.risk_manager.validate_trade(
                        strategy_name=strategy["title"],
                        account_balance=self.trade_executor.get_available_balance(asset),
                        entry_price=trade_details["price"],
                        stop_loss=trade_details["stop_loss"]
                    ):
                        await self.trade_executor.execute_trade(strategy["title"], trade_details)

                # Monitor exit conditions
                active_trade = self.trade_manager.get_active_trade(strategy["id"], asset)
                if active_trade and self.evaluate_conditions(strategy_data["conditions"]["exit"], market_data):
                    await self.trade_executor.close_trade(active_trade)
        except Exception as e:
            self.logger.error(f"Error monitoring strategy '{strategy['title']}': {e}")

    async def check_trade_conditions(self, trade):
        """
        Checks conditions for an active trade.
        """
        try:
            market_data = await self.fetch_market_data(trade["asset"])
            if not market_data:
                self.logger.warning(f"No market data available for trade {trade['trade_id']}. Skipping.")
                return

            entry_price = float(trade.get("entry_price", 0))
            stop_loss = float(trade.get("stop_loss", 0))
            take_profit = float(trade.get("take_profit", 0))

            # Check stop-loss
            if stop_loss and market_data["price"] <= stop_loss:
                self.logger.info(f"Trade {trade['trade_id']} hit stop-loss at {market_data['price']}.")
                await self.trade_executor.close_trade(trade["trade_id"], "stop_loss")
                return

            # Check take-profit
            if take_profit and market_data["price"] >= take_profit:
                self.logger.info(f"Trade {trade['trade_id']} hit take-profit at {market_data['price']}.")
                await self.trade_executor.close_trade(trade["trade_id"], "take_profit")
                return

            self.logger.debug(f"Trade {trade['trade_id']} remains active.")
        except Exception as e:
            self.logger.error(f"Error checking conditions for trade {trade['trade_id']}: {e}")

    async def fetch_market_data(self, asset):
        """
        Fetches live market data for a given asset.
        """
        try:
            market_data = await self.trade_executor.fetch_market_data(asset)
            self.logger.debug(f"Market data for {asset}: {market_data}")
            return market_data
        except Exception as e:
            self.logger.error(f"Error fetching market data for {asset}: {e}")
            return {}

    def evaluate_conditions(self, conditions, market_data):
        """
        Evaluates entry or exit conditions from the strategy JSON.
        """
        try:
            for condition in conditions:
                indicator = condition["indicator"]
                operator = condition["operator"]
                value = float(condition["value"])
                current_value = market_data.get(indicator)

                if current_value is None or not self.compare(operator, current_value, value):
                    return False
            return True
        except Exception as e:
            self.logger.error(f"Error evaluating conditions: {e}")
            return False

    @staticmethod
    def compare(operator, current_value, target_value):
        """
        Compares two values based on the specified operator.
        """
        operators = {
            ">": lambda x, y: x > y,
            "<": lambda x, y: x < y,
            ">=": lambda x, y: x >= y,
            "<=": lambda x, y: x <= y,
            "==": lambda x, y: x == y,
        }
        return operators[operator](current_value, target_value)
