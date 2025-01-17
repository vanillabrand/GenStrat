import logging
from typing import Dict, List
import redis
import asyncio

class TradeManager:
    """
    Manages the lifecycle of trades, including recording, updating, retrieving, transitioning,
    archiving, and closing trades. Supports handling both pending and active trades with advanced states.
    """

    def __init__(self, redis_host="localhost", redis_port=6379, redis_db=0):
        self.redis_client = redis.StrictRedis(
            host=redis_host, port=redis_port, db=redis_db, decode_responses=True
        )
        self.logger = logging.getLogger(self.__class__.__name__)
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    ### --- Utility Methods ---

    def _fetch_trades_by_ids(self, trade_ids: List[str]) -> List[Dict]:
        """
        Fetches trade data for multiple trade IDs in one Redis call.
        """
        try:
            trades = [self.redis_client.hgetall(f"trade:{trade_id}") for trade_id in trade_ids]
            return trades
        except Exception as e:
            self.logger.error(f"Error fetching trades by IDs: {e}")
            return []

    def _update_trade_status(self, trade_id: str, new_status: str):
        """
        Updates the status of a trade.
        """
        key = f"trade:{trade_id}"
        if self.redis_client.exists(key):
            self.redis_client.hset(key, "status", new_status)
            self.logger.info(f"Trade {trade_id} status updated to {new_status}.")
        else:
            self.logger.error(f"Trade {trade_id} does not exist.")

    ### --- Trade Recording and State Management ---

    def record_trade(self, trade_data: Dict):
        """
        Records a new trade and sets its initial status.
        """
        try:
            trade_id = trade_data["trade_id"]
            key = f"trade:{trade_id}"
            trade_data["status"] = "pending"
            trade_data.setdefault("retry_count", 0)
            trade_data.setdefault("fallback_executed", False)
            self.redis_client.hmset(key, trade_data)
            self.redis_client.sadd("pending_trades", trade_id)
            self.logger.info(f"Recorded new trade: {trade_id}")
        except Exception as e:
            self.logger.error(f"Failed to record trade: {e}")

    def add_failed_trade(self, trade_data: Dict):
        """
        Adds a failed trade back to the pending queue for retry.
        """
        try:
            trade_id = trade_data["trade_id"]
            trade_data["status"] = "pending"
            trade_data["retry_count"] += 1
            self.redis_client.hmset(f"trade:{trade_id}", trade_data)
            self.redis_client.sadd("pending_trades", trade_id)
            self.logger.warning(f"Requeued failed trade: {trade_id}. Retry count: {trade_data['retry_count']}")
        except Exception as e:
            self.logger.error(f"Failed to requeue trade {trade_id}: {e}")

    def transition_trade(self, trade_id: str, from_set: str, to_set: str, new_status: str):
        """
        Transitions a trade between Redis sets and updates its status.
        """
        key = f"trade:{trade_id}"
        try:
            if self.redis_client.exists(key):
                self.redis_client.srem(from_set, trade_id)
                self.redis_client.sadd(to_set, trade_id)
                self._update_trade_status(trade_id, new_status)
            else:
                self.logger.error(f"Trade ID '{trade_id}' does not exist.")
        except Exception as e:
            self.logger.error(f"Failed to transition trade {trade_id} from {from_set} to {to_set}: {e}")

    def transition_to_active(self, trade_id: str):
        """
        Moves a trade from pending to active status.
        """
        self.transition_trade(trade_id, "pending_trades", "active_trades", "active")

    def transition_to_closed(self, trade_id: str):
        """
        Moves a trade to the closed state.
        """
        self.transition_trade(trade_id, "active_trades", "closed_trades", "closed")

    def archive_trade(self, trade_id: str):
        """
        Archives a trade and removes it from active storage.
        """
        key = f"trade:{trade_id}"
        archive_key = f"archive:trade:{trade_id}"
        try:
            if self.redis_client.exists(key):
                trade_data = self.redis_client.hgetall(key)
                self.redis_client.set(archive_key, json.dumps(trade_data))
                self.redis_client.delete(key)
                self.logger.info(f"Trade {trade_id} archived successfully.")
            else:
                self.logger.error(f"Trade ID '{trade_id}' does not exist.")
        except Exception as e:
            self.logger.error(f"Failed to archive trade {trade_id}: {e}")

    ### --- Trade Retrieval and Monitoring ---

    def get_active_trades(self) -> List[Dict]:
        """
        Retrieves all active trades from the database.
        """
        try:
            trade_ids = self.redis_client.smembers("active_trades")
            trades = self._fetch_trades_by_ids(trade_ids)
            return trades
        except Exception as e:
            self.logger.error(f"Failed to retrieve active trades: {e}")
            return []

    def get_pending_trades(self) -> List[Dict]:
        """
        Retrieves all pending trades from the database.
        """
        try:
            trade_ids = self.redis_client.smembers("pending_trades")
            trades = self._fetch_trades_by_ids(trade_ids)
            return trades
        except Exception as e:
            self.logger.error(f"Failed to retrieve pending trades: {e}")
            return []

    async def monitor_pending_trades(self, market_monitor, trade_executor):
        """
        Asynchronously monitors pending trades and executes them when entry conditions are met.
        """
        self.logger.info("Starting trade monitoring loop...")
        while True:
            pending_trades = self.get_pending_trades()
            tasks = [
                self._process_trade(trade, market_monitor, trade_executor)
                for trade in pending_trades
            ]
            await asyncio.gather(*tasks)
            await asyncio.sleep(5)

    async def _process_trade(self, trade: Dict, market_monitor, trade_executor):
        """
        Processes a single pending trade.
        """
        try:
            if market_monitor.check_entry_conditions(trade):
                self.logger.info(f"Entry condition met for {trade['asset']}. Executing trade.")
                await trade_executor.execute_trade(
                    trade["strategy_name"],
                    trade["asset"],
                    trade["side"],
                    trade
                )
                self.transition_to_active(trade["trade_id"])
            else:
                self.logger.debug(f"Conditions not met for {trade['asset']}. Trade remains pending.")
        except Exception as e:
            self.logger.error(f"Error processing trade {trade['trade_id']}: {e}")
