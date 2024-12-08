# performance_manager.py

import redis
import json
from config import REDIS_HOST, REDIS_PORT, REDIS_DB
import logging
from datetime import datetime

class PerformanceManager:
    def __init__(self):
        self.redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
        self.logger = logging.getLogger(self.__class__.__name__)

    def record_performance(self, strategy_name, performance_data):
        key = f"performance:{strategy_name}"
        date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        data = {
            'date': date_str,
            **performance_data
        }
        self.redis_client.rpush(key, json.dumps(data))
        self.logger.info(f"Recorded performance data for strategy '{strategy_name}' on {date_str}.")

    def get_performance_data(self, strategy_name):
        key = f"performance:{strategy_name}"
        data_list = self.redis_client.lrange(key, 0, -1)
        performance_data = []
        for data in data_list:
            performance_data.append(json.loads(data))
        self.logger.debug(f"Retrieved performance data for strategy '{strategy_name}'.")
        return performance_data

    def clear_performance_data(self, strategy_name):
        key = f"performance:{strategy_name}"
        self.redis_client.delete(key)
        self.logger.info(f"Cleared performance data for strategy '{strategy_name}'.")
