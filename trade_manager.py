import logging
from typing import Dict, List
import redis
import json
import asyncio


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

    ### --- Trade Recording and State Management ---

    def record_trade(self, trade_data: Dict):
        """
        Records a new trade and sets its status to pending.
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

    def add_failed_trade(self, strategy_name, asset, side, strategy_data):
        """
        Adds a trade back to the pending queue if it fails execution.
        """
        try:
            trade_id = f"{strategy_name}_{asset}_{side}"
            trade_data = {
                "trade_id": trade_id,
                "strategy_name": strategy_name,
                "asset": asset,
                "side": side,
                "status": "pending",
                "retry_count": strategy_data.get("retry_count", 0) + 1
            }
            self.redis_client.hmset(f"trade:{trade_id}", trade_data)
            self.redis_client.sadd("pending_trades", trade_id)
            self.logger.warning(f"Requeued failed trade: {trade_id}. Retry count: {trade_data['retry_count']}")
        except Exception as e:
            self.logger.error(f"Failed to requeue trade for {strategy_name}: {e}")

    def transition_to_active(self, trade_id: str):
        """
        Moves a trade from pending to active status.
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

    def transition_to_closed(self, trade_id: str):
        """
        Moves a trade to the closed state.
        """
        key = f"trade:{trade_id}"
        try:
            if self.redis_client.exists(key):
                self.redis_client.srem("active_trades", trade_id)
                self.redis_client.sadd("closed_trades", trade_id)
                self.redis_client.hset(key, "status", "closed")
                self.logger.info(f"Trade {trade_id} marked as closed.")
            else:
                self.logger.error(f"Trade ID '{trade_id}' does not exist.")
        except Exception as e:
            self.logger.error(f"Failed to transition trade {trade_id} to closed: {e}")


    def close_trade(self, trade_id: str):
        """
        Marks a trade as closed and removes it from the active trades list.
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

    ### --- Trade Retrieval and Monitoring ---

    def get_active_trades(self) -> List[Dict]:
        """
        Retrieves all active trades from the database.
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
        """
        try:
            trade_ids = self.redis_client.smembers("pending_trades")
            trades = [self.redis_client.hgetall(f"trade:{trade_id}") for trade_id in trade_ids]
            self.logger.debug(f"Retrieved {len(trades)} pending trades.")
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
            for trade in pending_trades:
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
                    self.logger.error(f"Error monitoring trade {trade['trade_id']}: {e}")
            await asyncio.sleep(5)  # Monitor every 5 seconds
