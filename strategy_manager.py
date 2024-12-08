# strategy_manager.py

import redis
import json
import uuid
import logging
from typing import Dict, List

from config import REDIS_HOST, REDIS_PORT, REDIS_DB


class StrategyManager:
    """
    Manages the storage, retrieval, and activation of trading strategies.
    Each strategy is assigned a unique ID and a user-defined title.
    """

    def __init__(self):
        self.redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
        self.logger = logging.getLogger(self.__class__.__name__)

    def generate_unique_id(self) -> str:
        """
        Generates a unique UUID for a new strategy.
        """
        return str(uuid.uuid4())

    def save_strategy(self, title: str, description: str, strategy_data: Dict) -> str:
        """
        Saves a new strategy with a unique ID and title.

        Returns:
            The unique ID of the saved strategy.
        """
        strategy_id = self.generate_unique_id()
        key = f"strategy:{strategy_id}"
        strategy_record = {
            "id": strategy_id,
            "title": title,
            "description": description,
            "data": json.dumps(strategy_data),
            "active": "False"
        }
        try:
            self.redis_client.hmset(key, strategy_record)
            self.logger.info(f"Strategy '{title}' with ID '{strategy_id}' saved successfully.")
            return strategy_id
        except Exception as e:
            self.logger.error(f"Failed to save strategy '{title}': {e}")
            raise

            

    def update_strategy(self, strategy_id: str, title: str, description: str, strategy_data: Dict):
        """
        Updates an existing strategy identified by its unique ID.
        """
        key = f"strategy:{strategy_id}"
        if not self.redis_client.exists(key):
            self.logger.error(f"Strategy with ID '{strategy_id}' does not exist.")
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")
        updated_record = {
            "title": title,
            "description": description,
            "data": json.dumps(strategy_data)
        }
        try:
            self.redis_client.hmset(key, updated_record)
            self.logger.info(f"Strategy '{title}' with ID '{strategy_id}' updated successfully.")
        except Exception as e:
            self.logger.error(f"Failed to update strategy '{title}': {e}")
            raise

    def update_risk_parameters(self, strategy_id: str, risk_params: Dict):
        """
        Updates the risk parameters of a strategy identified by its unique ID.
        """
        key = f"strategy:{strategy_id}"
        if not self.redis_client.exists(key):
            self.logger.error(f"Strategy with ID '{strategy_id}' does not exist.")
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")
        try:
            data = self.redis_client.hget(key, "data")
            strategy_data = json.loads(data)
            strategy_data['risk_management'] = risk_params
            self.redis_client.hset(key, "data", json.dumps(strategy_data))
            self.logger.info(f"Risk parameters for strategy ID '{strategy_id}' updated successfully.")
        except Exception as e:
            self.logger.error(f"Failed to update risk parameters for strategy ID '{strategy_id}': {e}")
            raise

    def load_strategy(self, strategy_id: str) -> Dict:
        """
        Loads a strategy by its unique ID.

        Returns:
            A dictionary containing the strategy data.
        """
        key = f"strategy:{strategy_id}"
        if not self.redis_client.exists(key):
            self.logger.error(f"Strategy with ID '{strategy_id}' does not exist.")
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")
        try:
            data = self.redis_client.hgetall(key)
            strategy_data = json.loads(data['data'])
            strategy_record = {
                "id": data['id'],
                "title": data['title'],
                "description": data['description'],
                "data": strategy_data,
                "active": data['active'] == "True"
            }
            self.logger.info(f"Strategy '{strategy_record['title']}' with ID '{strategy_id}' loaded successfully.")
            return strategy_record
        except Exception as e:
            self.logger.error(f"Failed to load strategy ID '{strategy_id}': {e}")
            raise

    def list_strategies(self) -> List[Dict]:
        """
        Lists all saved strategies with their IDs and titles.

        Returns:
            A list of dictionaries containing strategy IDs, titles, and activation status.
        """
        try:
            keys = self.redis_client.keys("strategy:*")
            strategies = []
            for key in keys:
                data = self.redis_client.hgetall(key)
                strategies.append({
                    "id": data['id'],
                    "title": data['title'],
                    "active": data['active'] == "True"
                })
            self.logger.info("Listed all strategies successfully.")
            return strategies
        except Exception as e:
            self.logger.error(f"Failed to list strategies: {e}")
            raise

    def activate_strategy(self, strategy_id: str):
        """
        Activates a strategy identified by its unique ID.
        """
        key = f"strategy:{strategy_id}"
        if not self.redis_client.exists(key):
            self.logger.error(f"Strategy with ID '{strategy_id}' does not exist.")
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")
        try:
            self.redis_client.hset(key, "active", "True")
            self.logger.info(f"Strategy ID '{strategy_id}' activated successfully.")
        except Exception as e:
            self.logger.error(f"Failed to activate strategy ID '{strategy_id}': {e}")
            raise

    def deactivate_strategy(self, strategy_id: str):
        """
        Deactivates a strategy identified by its unique ID.
        """
        key = f"strategy:{strategy_id}"
        if not self.redis_client.exists(key):
            self.logger.error(f"Strategy with ID '{strategy_id}' does not exist.")
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")
        try:
            self.redis_client.hset(key, "active", "False")
            self.logger.info(f"Strategy ID '{strategy_id}' deactivated successfully.")
        except Exception as e:
            self.logger.error(f"Failed to deactivate strategy ID '{strategy_id}': {e}")
            raise

    def remove_strategy(self, strategy_id: str):
        """
        Removes a strategy identified by its unique ID from the database.
        """
        key = f"strategy:{strategy_id}"
        if not self.redis_client.exists(key):
            self.logger.error(f"Strategy with ID '{strategy_id}' does not exist.")
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")
        try:
            self.redis_client.delete(key)
            self.logger.info(f"Strategy ID '{strategy_id}' removed successfully.")
        except Exception as e:
            self.logger.error(f"Failed to remove strategy ID '{strategy_id}': {e}")
            raise

    def get_active_strategies(self) -> List[Dict]:
        """
        Retrieves all active strategies.

        Returns:
            A list of dictionaries containing active strategy IDs and data.
        """
        try:
            keys = self.redis_client.keys("strategy:*")
            active_strategies = []
            for key in keys:
                data = self.redis_client.hgetall(key)
                if data['active'] == "True":
                    strategy_data = json.loads(data['data'])
                    active_strategies.append({
                        "id": data['id'],
                        "title": data['title'],
                        "strategy_data": strategy_data
                    })
            self.logger.info("Retrieved active strategies successfully.")
            return active_strategies
        except Exception as e:
            self.logger.error(f"Failed to retrieve active strategies: {e}")
            raise

    def is_strategy_complete(self, strategy_id: str) -> bool:
        """
        Checks if a strategy has all required parameters.

        Returns:
            True if complete, False otherwise.
        """
        key = f"strategy:{strategy_id}"
        if not self.redis_client.exists(key):
            self.logger.error(f"Strategy with ID '{strategy_id}' does not exist.")
            return False
        try:
            data = self.redis_client.hget(key, "data")
            strategy_data = json.loads(data)
            required_keys = ["strategy_name", "market_type", "assets", "trade_parameters", "conditions", "risk_management"]
            is_complete = all(k in strategy_data and strategy_data[k] for k in required_keys)
            self.logger.debug(f"Strategy ID '{strategy_id}' completeness: {is_complete}")
            return is_complete
        except Exception as e:
            self.logger.error(f"Error checking completeness for strategy ID '{strategy_id}': {e}")
            return False
