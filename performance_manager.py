import redis
import json
from datetime import datetime, timedelta
import logging
from typing import List, Dict

class PerformanceManager:
    """
    Manages the recording, retrieval, and analysis of strategy performance data.
    """

    def __init__(self, redis_host='localhost', redis_port=6379, redis_db=0):
        self.redis_client = redis.StrictRedis(host=redis_host, port=redis_port, db=redis_db, decode_responses=True)
        self.logger = logging.getLogger(self.__class__.__name__)

    def record_performance(self, strategy_id: str, performance_data: Dict):
        """
        Records performance data for a specific strategy.
        :param strategy_id: The ID of the strategy.
        :param performance_data: Dictionary containing performance metrics (e.g., profit, trades, etc.).
        """
        key = f"performance:{strategy_id}"
        date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        record = {
            'date': date_str,
            **performance_data
        }
        try:
            self.redis_client.rpush(key, json.dumps(record))
            self.logger.info(f"Recorded performance data for strategy '{strategy_id}' on {date_str}.")
        except Exception as e:
            self.logger.error(f"Failed to record performance data for strategy '{strategy_id}': {e}")

    def get_performance_data(self, strategy_id: str, start_date: str = None, end_date: str = None) -> List[Dict]:
        """
        Retrieves performance data for a strategy, optionally filtered by date range.
        :param strategy_id: The ID of the strategy.
        :param start_date: Optional start date for filtering (format: YYYY-MM-DD).
        :param end_date: Optional end date for filtering (format: YYYY-MM-DD).
        :return: List of performance data dictionaries.
        """
        key = f"performance:{strategy_id}"
        try:
            data_list = self.redis_client.lrange(key, 0, -1)
            performance_data = [json.loads(data) for data in data_list]

            if start_date or end_date:
                start_date = datetime.strptime(start_date, '%Y-%m-%d') if start_date else datetime.min
                end_date = datetime.strptime(end_date, '%Y-%m-%d') if end_date else datetime.max

                performance_data = [
                    data for data in performance_data
                    if start_date <= datetime.strptime(data['date'], '%Y-%m-%d %H:%M:%S') <= end_date
                ]

            self.logger.debug(f"Retrieved {len(performance_data)} performance records for strategy '{strategy_id}'.")
            return performance_data
        except Exception as e:
            self.logger.error(f"Failed to retrieve performance data for strategy '{strategy_id}': {e}")
            return []

    def calculate_summary(self, strategy_id: str) -> Dict:
        """
        Calculates summary statistics for a strategy's performance.
        :param strategy_id: The ID of the strategy.
        :return: Dictionary containing summary metrics (e.g., total profit, success rate, etc.).
        """
        performance_data = self.get_performance_data(strategy_id)
        if not performance_data:
            return {
                'total_trades': 0,
                'total_profit': 0,
                'success_rate': 0
            }

        total_trades = len(performance_data)
        total_profit = sum(float(data.get('profit', 0)) for data in performance_data)
        successful_trades = sum(1 for data in performance_data if float(data.get('profit', 0)) > 0)
        success_rate = (successful_trades / total_trades * 100) if total_trades > 0 else 0

        summary = {
            'total_trades': total_trades,
            'total_profit': total_profit,
            'success_rate': success_rate
        }
        self.logger.info(f"Calculated summary for strategy '{strategy_id}': {summary}")
        return summary

    def clear_performance_data(self, strategy_id: str):
        """
        Clears all performance data for a specific strategy.
        :param strategy_id: The ID of the strategy.
        """
        key = f"performance:{strategy_id}"
        try:
            self.redis_client.delete(key)
            self.logger.info(f"Cleared performance data for strategy '{strategy_id}'.")
        except Exception as e:
            self.logger.error(f"Failed to clear performance data for strategy '{strategy_id}': {e}")

    def get_performance_summary_table(self, strategy_id: str) -> str:
        """
        Generates a tabular summary of performance data for display.
        :param strategy_id: The ID of the strategy.
        :return: Formatted string of performance data.
        """
        performance_data = self.get_performance_data(strategy_id)
        if not performance_data:
            return f"No performance data available for strategy '{strategy_id}'."

        table = [
            f"{'Date':<20}{'Profit':<10}{'Trades':<10}"
        ]
        for data in performance_data:
            date = data['date']
            profit = float(data.get('profit', 0))
            trades = data.get('trades', '-')
            table.append(f"{date:<20}{profit:<10.2f}{trades:<10}")

        return '\n'.join(table)

    def delete_old_performance_data(self, strategy_id: str, days: int):
        """
        Deletes performance data older than the specified number of days.
        :param strategy_id: The ID of the strategy.
        :param days: The age threshold in days for deleting old data.
        """
        key = f"performance:{strategy_id}"
        try:
            data_list = self.redis_client.lrange(key, 0, -1)
            cutoff_date = datetime.now() - timedelta(days=days)

            updated_data = [
                data for data in data_list
                if datetime.strptime(json.loads(data)['date'], '%Y-%m-%d %H:%M:%S') > cutoff_date
            ]

            self.redis_client.delete(key)
            for data in updated_data:
                self.redis_client.rpush(key, data)

            self.logger.info(f"Deleted old performance data for strategy '{strategy_id}' older than {days} days.")
        except Exception as e:
            self.logger.error(f"Failed to delete old performance data for strategy '{strategy_id}': {e}")
