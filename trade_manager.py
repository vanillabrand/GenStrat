import threading
import logging
import redis
from typing import Dict, List
from datetime import datetime


class TradeManager:
    """
    Manages trade records, including recording new trades, updating trades,
    retrieving trade information, and storing trades in Redis for persistence.
    """

    def __init__(self, redis_host='localhost', redis_port=6379, redis_db=1):
        self.redis_client = redis.StrictRedis(host=redis_host, port=redis_port, db=redis_db, decode_responses=True)
        self.lock = threading.Lock()
        self.logger = logging.getLogger(self.__class__.__name__)

    def record_trade(self, trade_data: Dict):
        """
        Records a new trade in Redis.
        """
        with self.lock:
            trade_id = trade_data.get('order_id')
            if trade_id is None:
                self.logger.error("Trade data must include 'order_id'.")
                return

            trade_data['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            key = f"trade:{trade_id}"
            try:
                self.redis_client.hmset(key, trade_data)
                self.logger.info(f"Trade {trade_id} recorded.")
            except Exception as e:
                self.logger.error(f"Failed to record trade {trade_id}: {e}")

    def update_trade(self, trade_id: str, update_data: Dict):
        """
        Updates an existing trade in Redis.
        """
        with self.lock:
            key = f"trade:{trade_id}"
            if not self.redis_client.exists(key):
                self.logger.error(f"Trade {trade_id} not found.")
                return

            try:
                self.redis_client.hmset(key, update_data)
                self.logger.info(f"Trade {trade_id} updated.")
            except Exception as e:
                self.logger.error(f"Failed to update trade {trade_id}: {e}")

    def get_trade(self, trade_id: str) -> Dict:
        """
        Retrieves a trade by its ID from Redis.
        """
        with self.lock:
            key = f"trade:{trade_id}"
            if not self.redis_client.exists(key):
                self.logger.error(f"Trade {trade_id} not found.")
                return {}
            try:
                trade = self.redis_client.hgetall(key)
                self.logger.info(f"Trade {trade_id} retrieved.")
                return trade
            except Exception as e:
                self.logger.error(f"Failed to retrieve trade {trade_id}: {e}")
                return {}

    def get_trades_by_strategy(self, strategy_name: str) -> List[Dict]:
        """
        Retrieves all trades associated with a specific strategy from Redis.
        """
        with self.lock:
            try:
                keys = self.redis_client.keys("trade:*")
                trades = []
                for key in keys:
                    trade = self.redis_client.hgetall(key)
                    if trade.get('strategy_name') == strategy_name:
                        trades.append(trade)
                self.logger.info(f"Retrieved trades for strategy {strategy_name}.")
                return trades
            except Exception as e:
                self.logger.error(f"Failed to retrieve trades for strategy {strategy_name}: {e}")
                return []

    def get_all_trades(self) -> List[Dict]:
        """
        Retrieves all trades from Redis.
        """
        with self.lock:
            try:
                keys = self.redis_client.keys("trade:*")
                trades = [self.redis_client.hgetall(key) for key in keys]
                self.logger.info("Retrieved all trades.")
                return trades
            except Exception as e:
                self.logger.error(f"Failed to retrieve all trades: {e}")
                return []

    def get_active_trades(self) -> List[Dict]:
        """
        Retrieves all active trades from Redis.

        Returns:
            List[Dict]: A list of active trade records.
        """
        with self.lock:
            try:
                keys = self.redis_client.keys("trade:*")
                active_trades = []
                for key in keys:
                    trade = self.redis_client.hgetall(key)
                    if trade.get('status') == 'active':
                        active_trades.append(trade)
                self.logger.info("Retrieved all active trades.")
                return active_trades
            except Exception as e:
                self.logger.error(f"Failed to retrieve active trades: {e}")
                return []

    def remove_trade(self, trade_id: str):
        """
        Removes a trade from Redis.
        """
        with self.lock:
            key = f"trade:{trade_id}"
            if not self.redis_client.exists(key):
                self.logger.error(f"Trade {trade_id} not found.")
                return

            try:
                self.redis_client.delete(key)
                self.logger.info(f"Trade {trade_id} removed.")
            except Exception as e:
                self.logger.error(f"Failed to remove trade {trade_id}: {e}")

    def calculate_trade_metrics(self) -> Dict:
        """
        Calculates basic trade metrics like total profit/loss and success rate.

        Returns:
            Dict: A dictionary with trade performance metrics.
        """
        trades = self.get_all_trades()
        if not trades:
            return {"total_trades": 0, "total_profit_loss": 0, "success_rate": 0}

        total_profit_loss = 0
        successful_trades = 0

        for trade in trades:
            try:
                profit = float(trade.get('profit', 0))
                total_profit_loss += profit
                if profit > 0:
                    successful_trades += 1
            except ValueError:
                self.logger.warning(f"Invalid profit value in trade: {trade}")

        total_trades = len(trades)
        success_rate = (successful_trades / total_trades * 100) if total_trades > 0 else 0

        metrics = {
            "total_trades": total_trades,
            "total_profit_loss": total_profit_loss,
            "success_rate": success_rate
        }
        self.logger.info(f"Calculated trade metrics: {metrics}")
        return metrics
