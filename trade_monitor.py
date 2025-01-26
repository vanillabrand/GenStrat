import logging
from typing import Dict, List
import asyncio


class TradeMonitor:
    """
    Handles trade execution, monitoring, and database synchronization.
    Integrates with MarketMonitor for real-time updates and manages trade lifecycles.
    """

    def __init__(self, db, exchange, market_monitor):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.db = db  # Database interface
        self.exchange = exchange  # Exchange client
        self.market_monitor = market_monitor  # Real-time market data manager
        self.monitored_trades = []  # Active trades being monitored

    async def load_trades_from_db(self):
        """
        Loads trades from the database into the monitor.
        """
        try:
            trades = await self.db.get_all("trades")  # Fetch all trades from the database
            self.monitored_trades = [trade for trade in trades if trade["status"] in ["pending", "open"]]
            self.logger.info(f"Loaded {len(self.monitored_trades)} trades from the database.")
        except Exception as e:
            self.logger.error(f"Failed to load trades from database: {e}")

    async def evaluate_trades(self, asset: str, market_data: Dict):
        """
        Evaluates all trades for the given asset using real-time market data.
        """
        try:
            relevant_trades = [trade for trade in self.monitored_trades if trade["asset"] == asset]

            for trade in relevant_trades:
                # Check entry conditions for pending trades
                if trade["status"] == "pending" and self._check_entry_conditions(trade, market_data):
                    self.logger.info(f"Entry conditions met for trade {trade['trade_id']} on {asset}.")
                    await self.execute_trade(trade)

                # Check exit conditions for open trades
                if trade["status"] == "open" and self._check_exit_conditions(trade, market_data):
                    self.logger.info(f"Exit conditions met for trade {trade['trade_id']} on {asset}.")
                    await self.close_trade(trade)
        except Exception as e:
            self.logger.error(f"Error evaluating trades for asset {asset}: {e}")

    async def execute_trade(self, trade: Dict):
        """
        Executes a trade and updates the database.
        """
        try:
            self.logger.info(f"Executing trade: {trade}")
            # Simulated exchange API call
            trade["status"] = "open"
            trade["last_updated"] = self._current_timestamp()
            await self.db.update("trades", trade["trade_id"], trade)  # Sync with database
            self.monitored_trades.append(trade)
        except Exception as e:
            self.logger.error(f"Error executing trade {trade['trade_id']}: {e}")

    async def close_trade(self, trade: Dict):
        """
        Closes a trade and updates the database.
        """
        try:
            self.logger.info(f"Closing trade: {trade}")
            # Simulated exchange API call
            trade["status"] = "closed"
            trade["last_updated"] = self._current_timestamp()
            await self.db.update("trades", trade["trade_id"], trade)  # Sync with database
            self.monitored_trades = [t for t in self.monitored_trades if t["trade_id"] != trade["trade_id"]]
        except Exception as e:
            self.logger.error(f"Error closing trade {trade['trade_id']}: {e}")

    async def add_or_update_trade(self, trade: Dict):
        """
        Adds a new trade to monitoring or updates an existing one.
        """
        try:
            existing_trade = next((t for t in self.monitored_trades if t["trade_id"] == trade["trade_id"]), None)
            if existing_trade:
                self.logger.info(f"Updating trade {trade['trade_id']} in monitoring.")
                existing_trade.update(trade)
            else:
                self.logger.info(f"Adding new trade {trade['trade_id']} to monitoring.")
                self.monitored_trades.append(trade)

            await self.db.update("trades", trade["trade_id"], trade)  # Ensure database sync
        except Exception as e:
            self.logger.error(f"Error adding/updating trade {trade['trade_id']}: {e}")

    async def deactivate_trade(self, trade_id: str):
        """
        Deactivates a specific trade by marking it as inactive and cleaning up resources.
        """
        try:
            trade = next((t for t in self.monitored_trades if t["trade_id"] == trade_id), None)
            if trade:
                trade["status"] = "inactive"
                trade["last_updated"] = self._current_timestamp()
                await self.db.update("trades", trade_id, trade)
                self.monitored_trades = [t for t in self.monitored_trades if t["trade_id"] != trade_id]
                self.logger.info(f"Trade {trade_id} has been deactivated.")
            else:
                self.logger.warning(f"Trade {trade_id} not found in monitoring.")
        except Exception as e:
            self.logger.error(f"Error deactivating trade {trade_id}: {e}")

    def _check_entry_conditions(self, trade: Dict, market_data: Dict) -> bool:
        """
        Evaluates if entry conditions are met for a trade.
        """
        try:
            entry_conditions = trade.get("entry_conditions", [])
            return all(self._evaluate_condition(market_data, condition) for condition in entry_conditions)
        except Exception as e:
            self.logger.error(f"Error checking entry conditions for trade {trade['trade_id']}: {e}")
            return False

    def _check_exit_conditions(self, trade: Dict, market_data: Dict) -> bool:
        """
        Evaluates if exit conditions are met for a trade.
        """
        try:
            exit_conditions = trade.get("exit_conditions", [])
            return all(self._evaluate_condition(market_data, condition) for condition in exit_conditions)
        except Exception as e:
            self.logger.error(f"Error checking exit conditions for trade {trade['trade_id']}: {e}")
            return False

    def _evaluate_condition(self, market_data: Dict, condition: Dict) -> bool:
        """
        Checks a single condition against market data.
        """
        try:
            indicator = condition["indicator"]
            operator = condition["operator"]
            value = condition["value"]
            data_value = market_data.get(indicator)
            return self._evaluate_operator(data_value, operator, value)
        except Exception as e:
            self.logger.error(f"Error evaluating condition: {e}")
            return False

    def _evaluate_operator(self, a, operator, b) -> bool:
        """
        Compares values based on the given operator.
        """
        ops = {"<": lambda x, y: x < y, ">": lambda x, y: x > y, "<=": lambda x, y: x <= y, ">=": lambda x, y: x >= y, "==": lambda x, y: x == y}
        return ops.get(operator, lambda x, y: False)(a, b)

    def _current_timestamp(self):
        """
        Returns the current timestamp in ISO format.
        """
        from datetime import datetime
        return datetime.utcnow().isoformat()
