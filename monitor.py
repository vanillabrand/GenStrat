import redis
import logging
import csv
from typing import List, Dict
from datetime import datetime

class Monitor:
    """
    Monitors and logs trades, integrating Redis for persistence and scalability.
    """

    def __init__(self, redis_host='localhost', redis_port=6379, redis_db=1):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.redis_client = redis.StrictRedis(host=redis_host, port=redis_port, db=redis_db, decode_responses=True)

    def log_trade(self, trade_info: Dict):
        """
        Logs the trade information to Redis.

        Args:
            trade_info (Dict): Dictionary containing trade details.
        """
        trade_info['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        trade_id = f"trade:{trade_info['timestamp']}"
        try:
            self.redis_client.hmset(trade_id, trade_info)
            self.logger.info(f"Trade logged: {trade_info}")
        except Exception as e:
            self.logger.error(f"Failed to log trade: {e}")

    def get_trades(self) -> List[Dict]:
        """
        Retrieves all logged trades from Redis.

        Returns:
            List[Dict]: List of trade details.
        """
        try:
            keys = self.redis_client.keys("trade:*")
            trades = []
            for key in keys:
                trade = self.redis_client.hgetall(key)
                trades.append(trade)
            self.logger.info("Retrieved all trades successfully.")
            return trades
        except Exception as e:
            self.logger.error(f"Failed to retrieve trades: {e}")
            return []

    def export_trades_to_csv(self, filename: str):
        """
        Exports the logged trades to a CSV file.

        Args:
            filename (str): The name of the CSV file.
        """
        trades = self.get_trades()
        if not trades:
            self.logger.info("No trades to export.")
            return

        keys = trades[0].keys()
        try:
            with open(filename, 'w', newline='') as output_file:
                dict_writer = csv.DictWriter(output_file, keys)
                dict_writer.writeheader()
                dict_writer.writerows(trades)
            self.logger.info(f"Trades exported to {filename}")
        except Exception as e:
            self.logger.error(f"Failed to export trades to CSV: {e}")

    def get_trade_metrics(self) -> Dict:
        """
        Calculates basic trade metrics.

        Returns:
            Dict: Dictionary containing metrics such as total profit/loss and total trades.
        """
        trades = self.get_trades()
        if not trades:
            return {"total_trades": 0, "total_profit_loss": 0}

        total_profit_loss = 0
        for trade in trades:
            try:
                profit = float(trade.get('profit', 0))
                total_profit_loss += profit
            except ValueError:
                self.logger.warning(f"Invalid profit value in trade: {trade}")

        metrics = {
            "total_trades": len(trades),
            "total_profit_loss": total_profit_loss
        }
        self.logger.info(f"Trade metrics calculated: {metrics}")
        return metrics
