from redis.asyncio import Redis
import json
import uuid
import logging
from typing import Dict, List
import asyncio

class StrategyManager:
    """
    Manages the storage, retrieval, editing, activation, and removal of trading strategies.
    Integrates with TradeMonitor and MarketMonitor for lifecycle and market condition monitoring.
    """

    STRATEGY_PREFIX = "strategy:"
    TRADE_PREFIX = "trade:"

    def __init__(self, trade_manager, trade_monitor, market_monitor=None, redis_host='localhost', redis_port=6379, redis_db=0):
        # Dependency injection: trade_manager and trade_monitor must be provided.
        self.trade_manager = trade_manager
        self.trade_monitor = trade_monitor
        self.market_monitor = market_monitor
        self.redis_client = Redis(
            host=redis_host, port=redis_port, db=redis_db, decode_responses=True
        )
        self.logger = logging.getLogger(self.__class__.__name__)
        logging.basicConfig(level=logging.INFO, 
                            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        self.db = redis_db

    @staticmethod
    def generate_unique_id() -> str:
        """Generates a unique ID for a strategy."""
        return str(uuid.uuid4())

    def set_monitoring(self, trade_monitor, market_monitor=None):
        """Assigns TradeMonitor and MarketMonitor instances for monitoring."""
        self.trade_monitor = trade_monitor
        self.market_monitor = market_monitor

    def validate_strategy_data(self, strategy_data: Dict):
        """
        Validates strategy data for required fields and structure.
        Raises a ValueError if any required field is missing or invalid.
        """
        required_fields = ['strategy_name', 'market_type', 'assets', 'trade_parameters', 'conditions', 'risk_management']
        for field in required_fields:
            if field not in strategy_data:
                raise ValueError(f"Strategy data must include '{field}'.")
        if not isinstance(strategy_data.get("assets"), list) or not strategy_data["assets"]:
            raise ValueError("Assets must be a non-empty list.")
        conditions = strategy_data.get("conditions", {})
        if not isinstance(conditions.get("entry"), list) or not conditions.get("entry"):
            raise ValueError("Entry conditions must be a non-empty list.")
        if not isinstance(conditions.get("exit"), list) or not conditions.get("exit"):
            raise ValueError("Exit conditions must be a non-empty list.")
        risk_management = strategy_data.get("risk_management", {})
        if not (0 < risk_management.get("stop_loss", 0) < 100):
            raise ValueError("Stop-loss must be between 0 and 100%.")
        if not (0 < risk_management.get("take_profit", 0) < 500):
            raise ValueError("Take-profit must be between 0 and 500%.")

    async def save_strategy(self, title: str, description: str, strategy_data: Dict, trades: List[Dict] = None) -> str:
        """
        Saves a new strategy to Redis.
        Returns the generated strategy ID.
        """
        strategy_id = self.generate_unique_id()
        key = f"{self.STRATEGY_PREFIX}{strategy_id}"
        strategy_record = {
            "id": strategy_id,
            "title": title,
            "description": description,
            "rationale": strategy_data.get("strategy_rationale", ""),
            "data": json.dumps(strategy_data),
            "active": "False",
            "trades": json.dumps(trades or [])
        }
        try:
            await self.redis_client.hset(key, mapping=strategy_record)
            self.logger.info(f"Strategy '{title}' with ID '{strategy_id}' saved successfully.")
            return strategy_id
        except Exception as e:
            self.logger.error(f"Failed to save strategy '{title}': {e}")
            raise

    async def load_strategy(self, strategy_id: str) -> Dict:
        """
        Loads a strategy from Redis.
        Returns the strategy as a dictionary.
        """
        key = f"{self.STRATEGY_PREFIX}{strategy_id}"
        if not await self.redis_client.exists(key):
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")
        try:
            strategy = await self.redis_client.hgetall(key)
            strategy["data"] = json.loads(strategy["data"])
            strategy["trades"] = json.loads(strategy["trades"])
            strategy["active"] = strategy["active"] == "True"
            return strategy
        except Exception as e:
            self.logger.error(f"Failed to load strategy '{strategy_id}': {e}")
            raise

    async def save_trades_to_strategy(self, strategy_id: str, trades: List[Dict]):
        """
        Saves trades to the strategy record in Redis.
        """
        try:
            key = f"{self.STRATEGY_PREFIX}{strategy_id}"
            if not await self.redis_client.exists(key):
                raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")
            await self.redis_client.hset(key, "trades", json.dumps(trades))
            self.logger.info(f"Trades saved to strategy {strategy_id}.")
        except Exception as e:
            self.logger.error(f"Failed to save trades to strategy {strategy_id}: {e}")
            raise

    async def activate_strategy(self, strategy_id: str):
        """
        Activates a strategy by marking it active in Redis and instructing MarketMonitor
        to begin monitoring its trades.
        """
        try:
            strategy = await self.load_strategy(strategy_id)
            if strategy["active"]:
                raise ValueError(f"Strategy '{strategy_id}' is already active.")
            await self.redis_client.hset(f"{self.STRATEGY_PREFIX}{strategy_id}", "active", "True")
            self.logger.info(f"Strategy '{strategy_id}' activated.")
            trades = strategy["trades"]
            if self.market_monitor:
                await self.market_monitor.monitor_strategy(strategy, trades)
            self.logger.info(f"Strategy '{strategy_id}' is now monitored.")
        except Exception as e:
            self.logger.error(f"Failed to activate strategy '{strategy_id}': {e}")
            raise

    async def deactivate_strategy(self, strategy_id: str):
        """
        Deactivates a strategy by marking it inactive in Redis and instructing MarketMonitor
        to stop monitoring it.
        """
        try:
            strategy = await self.load_strategy(strategy_id)
            if not strategy["active"]:
                raise ValueError(f"Strategy '{strategy_id}' is not active.")
            await self.redis_client.hset(f"{self.STRATEGY_PREFIX}{strategy_id}", "active", "False")
            self.logger.info(f"Strategy '{strategy_id}' deactivated.")
            if self.market_monitor:
                await self.market_monitor.deactivate_strategy(strategy_id)
            self.logger.info(f"Strategy '{strategy_id}' is no longer monitored.")
        except Exception as e:
            self.logger.error(f"Failed to deactivate strategy '{strategy_id}': {e}")
            raise

    async def activate_strategy_with_trades(self, strategy_id: str, budget: float) -> str:
        """
        Activates a strategy and ensures that it has valid trades.
        If no valid trades exist (or all are inactive/cancelled), it uses the
        TradeSuggestionManager to generate new trades. New trades are then added
        via TradeManager and MarketMonitor begins monitoring.
        Returns the strategy_id on successful activation.
        """
        try:
            strategy = await self.load_strategy(strategy_id)
            if strategy is None:
                raise ValueError(f"Strategy {strategy_id} not found.")
            if str(strategy.get("active", "False")).lower() == "true":
                raise ValueError(f"Strategy {strategy_id} is already active.")
            await self._activate_in_db(strategy_id)
            # Retrieve trades using the trade_manager.
            all_trades = self.trade_manager.get_strategy_trades(strategy_id)
            valid_trades = [t for t in all_trades if t.get("status", "").lower() not in ("inactive", "cancelled")]
            if not valid_trades:
                self.logger.info(f"No active trades found for strategy {strategy_id}; generating new trades.")
                # Defensive check: Ensure that MarketMonitor.trade_suggestion_manager is set.
                if self.market_monitor is None or self.market_monitor.trade_suggestion_manager is None:
                    raise ValueError("TradeSuggestionManager is not set in MarketMonitor.")
                new_trades = await self.market_monitor.trade_suggestion_manager.generate_trades(
                    strategy_id, strategy.get("data", {}), {}, budget
                )
                if not new_trades:
                    raise ValueError("Trade suggestion engine did not generate any trades. Please review strategy parameters.")
                for trade in new_trades:
                    await self.trade_manager.add_trade(trade)
                valid_trades = new_trades
            if self.market_monitor is not None:
                await self.market_monitor.monitor_strategy(strategy, valid_trades)
            self.logger.info(f"Strategy {strategy_id} activated with {len(valid_trades)} trades.")
            return strategy_id
        except Exception as e:
            self.logger.error(f"Failed to activate strategy {strategy_id} with trades: {e}", exc_info=True)
            raise

    async def _activate_in_db(self, strategy_id: str):
        """
        Internal method to mark the strategy as active in the database.
        """
        try:
            key = f"{self.STRATEGY_PREFIX}{strategy_id}"
            await asyncio.to_thread(self.redis_client.hset, key, "active", "True")
            self.logger.info(f"Strategy {strategy_id} marked as active in the database.")
        except Exception as e:
            self.logger.error(f"Failed to mark strategy {strategy_id} as active in DB: {e}", exc_info=True)
            raise

    async def list_strategies(self) -> List[Dict]:
        """
        Lists all saved strategies from Redis.
        Returns a list of strategy dictionaries.
        """
        try:
            keys = await self.redis_client.keys(f"{self.STRATEGY_PREFIX}*")
            strategies = []
            for key in keys:
                data = await self.redis_client.hgetall(key)
                if not data:
                    continue
                strategy_data = json.loads(data.get("data", "{}"))
                strategies.append({
                    "id": data.get("id"),
                    "title": data.get("title"),
                    "description": data.get("description"),
                    "rationale": data.get("rationale"),
                    "active": data.get("active") == "True",
                    "market_type": strategy_data.get("market_type", ""),
                    "assets": strategy_data.get("assets", []),
                    "trades": json.loads(data.get("trades", "[]"))
                })
            return strategies
        except Exception as e:
            self.logger.error(f"Failed to list strategies: {e}")
            return []

    async def edit_strategy(self, strategy_id: str, updates: Dict):
        """
        Edits an existing strategy in Redis and updates monitoring if active.
        """
        try:
            key = f"{self.STRATEGY_PREFIX}{strategy_id}"
            strategy = await self.load_strategy(strategy_id)
            updated_data = {**strategy["data"], **updates.get("data", {})}
            self.validate_strategy_data(updated_data)
            updated_strategy = {
                "id": strategy_id,
                "title": updates.get("title", strategy["title"]),
                "description": updates.get("description", strategy["description"]),
                "data": json.dumps(updated_data),
                "active": strategy["active"],
                "trades": json.dumps(updates.get("trades", strategy["trades"]))
            }
            await self.redis_client.hset(key, mapping=updated_strategy)
            self.logger.info(f"Strategy '{strategy_id}' updated successfully.")
            if strategy["active"] and self.market_monitor:
                await self.market_monitor.update_monitored_strategy(updated_strategy)
        except Exception as e:
            self.logger.error(f"Failed to edit strategy '{strategy_id}': {e}")
            raise

    async def remove_strategy(self, strategy_id: str):
        """
        Removes a strategy from Redis along with its associated trades.
        Also deactivates the strategy in MarketMonitor if applicable.
        Raises a ValueError if the strategy does not exist.
        """
        key = f"{self.STRATEGY_PREFIX}{strategy_id}"
        try:
            exists = await self.redis_client.exists(key)
            if not exists:
                raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")
            await self.redis_client.delete(key)
            self.logger.info(f"Strategy '{strategy_id}' removed successfully.")
            # If MarketMonitor is set and supports deactivation, call it.
            if self.market_monitor is not None and hasattr(self.market_monitor, "deactivate_strategy"):
                await self.market_monitor.deactivate_strategy(strategy_id)
                self.logger.info(f"Strategy '{strategy_id}' removed from live monitoring.")
        except Exception as e:
            self.logger.error(f"Failed to remove strategy '{strategy_id}': {e}", exc_info=True)
            raise
