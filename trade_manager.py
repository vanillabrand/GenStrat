import logging
from typing import Dict, List
import redis
import json


class TradeManager:
    """
    Manages the lifecycle of trades, including recording, updating, retrieving, transitioning,
    and closing trades. Supports handling both pending and active trades.
    """

    def __init__(self, redis_host="localhost", redis_port=6379, redis_db=0):
        self.redis_client = redis.StrictRedis(
            host=redis_host, port=redis_port, db=redis_db, decode_responses=True
        )
        self.logger = logging.getLogger(self.__class__.__name__)
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    def record_trade(self, trade_data: Dict):
        """
        Records a new trade in the database and sets its status to pending.
        :param trade_data: Dictionary containing trade details.
        """
        try:
            trade_id = trade_data["trade_id"]
            key = f"trade:{trade_id}"
            trade_data["status"] = "pending"
            self.redis_client.hmset(key, trade_data)
            self.redis_client.sadd("pending_trades", trade_id)
            self.logger.info(f"Recorded new trade: {trade_id}")
        except Exception as e:
            self.logger.error(f"Failed to record trade: {e}")

    def get_active_trades(self) -> List[Dict]:
        """
        Retrieves all active trades from the database.
        :return: List of dictionaries representing active trades.
        """
        try:
            trade_ids = self.redis_client.smembers("active_trades")
            trades = [self.redis_client.hgetall(f"trade:{trade_id}") for trade_id in trade_ids]
            self.logger.debug(f"Retrieved {len(trades)} active trades.")
            return trades
        except Exception as e:
            self.logger.error(f"Failed to retrieve active trades: {e}")
            return []

    def get_pending_trades(self) -> List[Dict]:
        """
        Retrieves all pending trades from the database.
        :return: List of dictionaries representing pending trades.
        """
        try:
            trade_ids = self.redis_client.smembers("pending_trades")
            trades = [self.redis_client.hgetall(f"trade:{trade_id}") for trade_id in trade_ids]
            self.logger.debug(f"Retrieved {len(trades)} pending trades.")
            return trades
        except Exception as e:
            self.logger.error(f"Failed to retrieve pending trades: {e}")
            return []

    def transition_to_active(self, trade_id: str):
        """
        Moves a trade from pending to active status.
        :param trade_id: Unique identifier of the trade.
        """
        key = f"trade:{trade_id}"
        try:
            if self.redis_client.exists(key):
                self.redis_client.srem("pending_trades", trade_id)
                self.redis_client.sadd("active_trades", trade_id)
                self.redis_client.hset(key, "status", "active")
                self.logger.info(f"Trade {trade_id} transitioned to active.")
            else:
                self.logger.error(f"Trade ID '{trade_id}' does not exist.")
        except Exception as e:
            self.logger.error(f"Failed to transition trade {trade_id} to active: {e}")

    def update_trade(self, trade_id: str, updates: Dict):
        """
        Updates the details of an existing trade.
        :param trade_id: Unique identifier of the trade.
        :param updates: Dictionary containing the fields to update.
        """
        try:
            key = f"trade:{trade_id}"
            if not self.redis_client.exists(key):
                self.logger.error(f"Trade ID '{trade_id}' does not exist.")
                return

            self.redis_client.hmset(key, updates)
            self.logger.info(f"Updated trade ID '{trade_id}' with {updates}")
        except Exception as e:
            self.logger.error(f"Failed to update trade ID '{trade_id}': {e}")

    def close_trade(self, trade_id: str):
        """
        Marks a trade as closed and removes it from the active trades list.
        :param trade_id: Unique identifier of the trade.
        """
        try:
            key = f"trade:{trade_id}"
            if self.redis_client.exists(key):
                self.redis_client.srem("active_trades", trade_id)
                self.redis_client.hset(key, "status", "closed")
                self.logger.info(f"Closed trade ID: {trade_id}")
            else:
                self.logger.error(f"Trade ID '{trade_id}' does not exist.")
        except Exception as e:
            self.logger.error(f"Failed to close trade ID '{trade_id}': {e}")

    def get_trade_by_id(self, trade_id: str) -> Dict:
        """
        Fetches a specific trade by its unique identifier.
        :param trade_id: Unique identifier of the trade.
        :return: Dictionary containing trade details.
        """
        try:
            key = f"trade:{trade_id}"
            if self.redis_client.exists(key):
                trade = self.redis_client.hgetall(key)
                self.logger.debug(f"Retrieved trade ID '{trade_id}': {trade}")
                return trade
            else:
                self.logger.warning(f"Trade ID '{trade_id}' does not exist.")
                return {}
        except Exception as e:
            self.logger.error(f"Failed to retrieve trade ID '{trade_id}': {e}")
            return {}

    def record_strategy_conditions(self, strategy_name: str, conditions: Dict):
        """
        Records the conditions for a specific strategy.
        :param strategy_name: Name of the strategy.
        :param conditions: Dictionary containing the conditions to save.
        """
        try:
            key = f"strategy_conditions:{strategy_name}"
            self.redis_client.hmset(key, {"data": json.dumps(conditions)})
            self.logger.info(f"Recorded conditions for strategy '{strategy_name}'.")
        except Exception as e:
            self.logger.error(f"Failed to record conditions for strategy '{strategy_name}': {e}")

    def get_strategy_conditions(self, strategy_name: str) -> Dict:
        """
        Retrieves the conditions for a specific strategy.
        :param strategy_name: Name of the strategy.
        :return: Dictionary containing the strategy's conditions.
        """
        try:
            key = f"strategy_conditions:{strategy_name}"
            if self.redis_client.exists(key):
                conditions = self.redis_client.hgetall(key)
                self.logger.debug(f"Retrieved conditions for strategy '{strategy_name}': {conditions}")
                return json.loads(conditions.get("data", "{}"))
            else:
                self.logger.warning(f"No conditions found for strategy '{strategy_name}'.")
                return {}
        except Exception as e:
            self.logger.error(f"Failed to retrieve conditions for strategy '{strategy_name}': {e}")
            return {}

    def clear_closed_trades(self):
        """
        Clears all closed trades from the database.
        """
        try:
            trade_ids = self.redis_client.smembers("active_trades")
            for trade_id in trade_ids:
                key = f"trade:{trade_id}"
                trade = self.redis_client.hgetall(key)
                if trade.get("status") == "closed":
                    self.redis_client.delete(key)
                    self.redis_client.srem("active_trades", trade_id)
                    self.logger.info(f"Cleared closed trade ID: {trade_id}")
        except Exception as e:
            self.logger.error(f"Failed to clear closed trades: {e}")
