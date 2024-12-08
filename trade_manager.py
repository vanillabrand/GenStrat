# trade_manager.py

import threading
import logging
from typing import Dict, List


class TradeManager:
    """
    Manages trade records, including recording new trades, updating trades,
    and retrieving trade information.
    """

    def __init__(self):
        self.trades = {}  # key: trade_id, value: trade data
        self.lock = threading.Lock()
        self.logger = logging.getLogger(self.__class__.__name__)

    def record_trade(self, trade_data: Dict):
        """
        Records a new trade.
        """
        with self.lock:
            trade_id = trade_data.get('order_id')
            if trade_id is None:
                self.logger.error("Trade data must include 'order_id'.")
                return
            self.trades[trade_id] = trade_data
            self.logger.info(f"Trade {trade_id} recorded.")

    def update_trade(self, trade_id: str, update_data: Dict):
        """
        Updates an existing trade.
        """
        with self.lock:
            if trade_id not in self.trades:
                self.logger.error(f"Trade {trade_id} not found.")
                return
            self.trades[trade_id].update(update_data)
            self.logger.info(f"Trade {trade_id} updated.")

    def get_trade(self, trade_id: str) -> Dict:
        """
        Retrieves a trade by its ID.
        """
        with self.lock:
            return self.trades.get(trade_id)

    def get_trades_by_strategy(self, strategy_name: str) -> List[Dict]:
        """
        Retrieves all trades associated with a specific strategy.
        """
        with self.lock:
            return [trade for trade in self.trades.values() if trade['strategy_name'] == strategy_name]

    def get_all_trades(self) -> List[Dict]:
        """
        Retrieves all trades.
        """
        with self.lock:
            return list(self.trades.values())

    def remove_trade(self, trade_id: str):
        """
        Removes a trade from the records.
        """
        with self.lock:
            if trade_id in self.trades:
                del self.trades[trade_id]
                self.logger.info(f"Trade {trade_id} removed.")
            else:
                self.logger.error(f"Trade {trade_id} not found.")
