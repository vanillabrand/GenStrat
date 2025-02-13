import redis
import json
from datetime import datetime, timedelta
import logging
from typing import List, Dict, Optional, Any

class PerformanceManager:
    """ 
    Manages the recording, retrieval, and analysis of strategy performance data.
    """

    def __init__(self, trade_manager, redis_host: str = 'localhost', redis_port: int = 6379, redis_db: int = 0):
        self.redis_client = redis.StrictRedis(
            host=redis_host, port=redis_port, db=redis_db, decode_responses=True
        )
        self.logger = logging.getLogger(self.__class__.__name__)
        self.trade_manager = trade_manager

    def record_performance(self, strategy_name: str, performance_data: Dict):
        """
        Records performance data for a specific strategy.
        :param strategy_name: The name of the strategy.
        :param performance_data: Dictionary containing performance metrics (e.g., profit, trades, etc.).
        """
        key = f"performance:{strategy_name}"
        date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        record = {
            'date': date_str,
            **performance_data
        }
        try:
            self.redis_client.rpush(key, json.dumps(record))
            self.logger.info(f"Recorded performance data for strategy '{strategy_name}' on {date_str}.")
        except Exception as e:
            self.logger.error(f"Failed to record performance data for strategy '{strategy_name}': {e}", exc_info=True)

    def get_performance_data(self, strategy_name: str, start_date: str = None, end_date: str = None) -> List[Dict]:
        """
        Retrieves performance data for a strategy, optionally filtered by a date range.
        :param strategy_name: The name of the strategy.
        :param start_date: Optional start date for filtering (format: YYYY-MM-DD).
        :param end_date: Optional end date for filtering (format: YYYY-MM-DD).
        :return: A list of performance data dictionaries.
        """
        key = f"performance:{strategy_name}"
        try:
            data_list = self.redis_client.lrange(key, 0, -1)
            performance_data = [json.loads(data) for data in data_list]

            if start_date or end_date:
                try:
                    start_dt = datetime.strptime(start_date, '%Y-%m-%d') if start_date else datetime.min
                    end_dt = datetime.strptime(end_date, '%Y-%m-%d') if end_date else datetime.max
                except ValueError as ve:
                    self.logger.warning(f"Invalid date format: {ve}. Returning all data.")
                    start_dt, end_dt = datetime.min, datetime.max

                performance_data = [
                    data for data in performance_data
                    if start_dt <= datetime.strptime(data.get('date', '1970-01-01 00:00:00'), '%Y-%m-%d %H:%M:%S') <= end_dt
                ]

            return performance_data
        except Exception as e:
            self.logger.error(f"Failed to retrieve performance data for strategy '{strategy_name}': {e}", exc_info=True)
            return []

    def calculate_summary(self, strategy_name: str) -> Dict:
        """
        Calculates summary statistics for a strategy's performance.
        Returns a dictionary with summary metrics (e.g., total profit, win rate, max drawdown).
        """
        performance_data = self.get_performance_data(strategy_name)
        if not performance_data:
            return {
                'total_trades': 0,
                'total_profit': 0.0,
                'success_rate': 0.0,
                'max_drawdown': 0.0
            }

        total_trades = len(performance_data)
        total_profit = sum(float(data.get('profit', 0)) for data in performance_data)
        successful_trades = len([data for data in performance_data if float(data.get('profit', 0)) > 0])
        success_rate = (successful_trades / total_trades * 100) if total_trades > 0 else 0.0

        equity_curve = []
        equity = 0.0
        max_drawdown = 0.0
        for data in performance_data:
            pnl = float(data.get('profit', 0))
            equity += pnl
            equity_curve.append(equity)
            if equity_curve:
                peak = max(equity_curve)
                drawdown = (peak - equity) / peak * 100 if peak > 0 else 0.0
                max_drawdown = max(max_drawdown, drawdown)

        summary = {
            'total_trades': total_trades,
            'total_profit': total_profit,
            'success_rate': success_rate,
            'max_drawdown': max_drawdown
        }
        self.logger.info(f"Calculated summary for strategy '{strategy_name}': {summary}")
        return summary

    def clear_performance_data(self, strategy_name: str):
        """
        Clears all performance data for a specific strategy.
        """
        key = f"performance:{strategy_name}"
        try:
            self.redis_client.delete(key)
            self.logger.info(f"Cleared performance data for strategy '{strategy_name}'.")
        except Exception as e:
            self.logger.error(f"Failed to clear performance data for strategy '{strategy_name}': {e}", exc_info=True)

    def delete_old_performance_data(self, strategy_name: str, days: int):
        """
        Deletes performance data older than the specified number of days.
        """
        key = f"performance:{strategy_name}"
        try:
            data_list = self.redis_client.lrange(key, 0, -1)
            cutoff_date = datetime.now() - timedelta(days=days)
            updated_data = [
                data for data in data_list
                if datetime.strptime(json.loads(data).get('date', '1970-01-01 00:00:00'), '%Y-%m-%d %H:%M:%S') > cutoff_date
            ]
            self.redis_client.delete(key)
            for data in updated_data:
                self.redis_client.rpush(key, data)
            self.logger.info(f"Deleted old performance data for strategy '{strategy_name}' older than {days} days. Removed {len(data_list) - len(updated_data)} records.")
        except Exception as e:
            self.logger.error(f"Failed to delete old performance data for strategy '{strategy_name}': {e}", exc_info=True)

    def get_active_trades(self, strategy_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieves a list of currently active trades. Filters by strategy_id if provided.
        """
        try:
            all_trades = self.trade_manager.get_all_trades()
            active_trades = [trade for trade in all_trades if trade.get("status") == "active"]
            if strategy_id:
                active_trades = [trade for trade in active_trades if trade.get("strategy_id") == strategy_id]
            self.logger.info(f"Active trades retrieved: {len(active_trades)} found.")
            return active_trades
        except Exception as e:
            self.logger.error(f"Error retrieving active trades: {e}", exc_info=True)
            return []

    def get_risk_metrics(self, strategy_name: str) -> Dict[str, Any]:
        """
        Returns risk metrics for the given strategy.
        Currently, this is a placeholder returning default values.
        You may integrate this with your risk management logic later.
        """
        return {
            "open_risk": 0.0,
            "used_margin": 0.0,
            "free_margin": 0.0,
            "margin_level": 0.0
        }
