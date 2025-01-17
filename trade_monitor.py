import logging
import redis
import json
import asyncio
from typing import List, Dict, Optional, Any


class TradeManager:
    """
    Manages the lifecycle of trades, including recording, updating, retrieving, transitioning,
    archiving, and revalidating trades. Supports handling both pending and active trades.
    """

    def __init__(self, redis_host="localhost", redis_port=6379, redis_db=0, trade_suggestion_manager=None):
        self.redis_client = redis.StrictRedis(
            host=redis_host, port=redis_port, db=redis_db, decode_responses=True
        )
        self.logger = logging.getLogger(self.__class__.__name__)
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        self.trade_suggestion_manager = trade_suggestion_manager
        self.market_monitor = None  # Set by MarketMonitor later

    ### --- Trade Recording and Retry Management ---

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

    ### --- Trade State Management ---

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

    def transition_trade(self, trade_id: str, from_set: str, to_set: str, new_status: str):
        """
        Transitions a trade between Redis sets and updates its status.
        """
        key = f"trade:{trade_id}"
        try:
            if self.redis_client.exists(key):
                self.redis_client.srem(from_set, trade_id)
                self.redis_client.sadd(to_set, trade_id)
                self.redis_client.hset(key, "status", new_status)
                self.logger.info(f"Trade {trade_id} transitioned to {new_status}.")
            else:
                self.logger.error(f"Trade ID '{trade_id}' does not exist.")
        except Exception as e:
            self.logger.error(f"Failed to transition trade {trade_id} from {from_set} to {to_set}: {e}")

    ### --- Pending Trades Management ---

    def get_pending_trades(self) -> List[Dict]:
        """
        Retrieves all pending trades from the database.
        """
        try:
            trade_ids = self.redis_client.smembers("pending_trades")
            trades = [self.redis_client.hgetall(f"trade:{trade_id}") for trade_id in trade_ids]
            self.logger.info(f"Retrieved {len(trades)} pending trades.")
            return trades
        except Exception as e:
            self.logger.error(f"Failed to retrieve pending trades: {e}")
            return []

    def retry_pending_trades(self):
        """
        Retries all pending trades that have failed or require reprocessing.
        """
        try:
            pending_trades = self.get_pending_trades()
            for trade in pending_trades:
                retry_count = int(trade.get("retry_count", 0))
                if retry_count >= 3:
                    self.logger.warning(f"Trade {trade['trade_id']} exceeded max retries. Archiving trade.")
                    self.transition_to_closed(trade["trade_id"])
                else:
                    self.logger.info(f"Retrying trade {trade['trade_id']} (Retry count: {retry_count}).")
                    self.add_failed_trade(trade)
        except Exception as e:
            self.logger.error(f"Error retrying pending trades: {e}")

    ### --- Trade Retrieval and Monitoring ---

    def get_active_trades(self, strategy_id: Optional[str] = None) -> List[Dict]:
        """
        Retrieves all active trades from the database. Filters by strategy_id if provided.
        """
        try:
            pattern = f"trade:{strategy_id}:*" if strategy_id else "trade:*"
            trade_keys = self.redis_client.keys(pattern)
            trades = [json.loads(self.redis_client.get(key)) for key in trade_keys]
            self.logger.info(f"Retrieved {len(trades)} active trades.")
            return trades
        except Exception as e:
            self.logger.error(f"Failed to retrieve active trades: {e}")
            return []

    ### --- MarketMonitor Integration ---

    def set_market_monitor(self, market_monitor):
        """
        Links MarketMonitor to TradeManager for trade updates.
        """
        self.market_monitor = market_monitor
        self.logger.info("MarketMonitor linked to TradeManager.")

    ### --- Trade Synchronization and Revalidation ---

    async def revalidate_trades(self, strategy_json: Dict[str, Any], market_data: Dict[str, Any], budget: float):
        """
        Periodically synchronizes active trades with OpenAI suggestions and market conditions.
        """
        strategy_id = strategy_json["strategy_name"]
        active_trades = self.get_active_trades(strategy_id)

        # Generate new trade suggestions
        new_trades = self.trade_suggestion_manager.generate_trades(strategy_json, market_data, budget)

        # Synchronize trades
        updated_trades = []
        for new_trade in new_trades:
            for active_trade in active_trades:
                if active_trade["trade_id"] == new_trade["trade_id"]:
                    # Update trade if needed
                    if active_trade != new_trade:
                        self.logger.info(f"Updating trade: {new_trade['trade_id']}")
                        self.save_trade(new_trade, strategy_id)
                        updated_trades.append(new_trade)
                    break
            else:
                # Add new trade
                self.logger.info(f"Adding new trade: {new_trade['trade_id']}")
                self.save_trade(new_trade, strategy_id)
                updated_trades.append(new_trade)

        # Archive removed trades
        removed_trades = [trade for trade in active_trades if trade not in updated_trades]
        self.archive_trades(strategy_id, removed_trades)

        # Notify MarketMonitor
        if self.market_monitor:
            self.market_monitor.on_trades_updated(strategy_id, updated_trades)
