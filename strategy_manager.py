import redis
import json
import uuid
import logging
from typing import Dict, List

class StrategyManager:
    """
    Manages the storage, retrieval, and activation of trading strategies.
    Each strategy is assigned a unique ID and a user-defined title.
    """

    def __init__(self, redis_host='localhost', redis_port=6379, redis_db=0):
        self.redis_client = redis.StrictRedis(host=redis_host, port=redis_port, db=redis_db, decode_responses=True)
        self.logger = logging.getLogger(self.__class__.__name__)

    def generate_unique_id(self) -> str:
        """
        Generates a unique UUID for a new strategy.
        """
        return str(uuid.uuid4())

    def save_strategy(self, title: str, description: str, strategy_data: Dict) -> str:
        """
        Saves a new strategy with a unique ID and title.
        :param title: Title of the strategy.
        :param description: Description of the strategy.
        :param strategy_data: Strategy parameters.
        :return: The unique ID of the saved strategy.
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

    def update_strategy(self, strategy_id: str, updates: Dict):
        """
        Updates an existing strategy with new data.
        :param strategy_id: The unique ID of the strategy.
        :param updates: Dictionary of fields to update.
        """
        key = f"strategy:{strategy_id}"
        if not self.redis_client.exists(key):
            self.logger.error(f"Strategy with ID '{strategy_id}' does not exist.")
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")
        try:
            existing_data = self.redis_client.hgetall(key)
            for field, value in updates.items():
                if field == 'data':
                    merged_data = json.loads(existing_data['data'])
                    merged_data.update(value)
                    updates['data'] = json.dumps(merged_data)
            self.redis_client.hmset(key, updates)
            self.logger.info(f"Strategy ID '{strategy_id}' updated successfully.")
        except Exception as e:
            self.logger.error(f"Failed to update strategy ID '{strategy_id}': {e}")
            raise

    def load_strategy(self, strategy_id: str) -> Dict:
        """
        Loads a strategy by its unique ID.
        :param strategy_id: The unique ID of the strategy.
        :return: A dictionary containing the strategy data.
        """
        key = f"strategy:{strategy_id}"
        if not self.redis_client.exists(key):
            self.logger.error(f"Strategy with ID '{strategy_id}' does not exist.")
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")
        try:
            data = self.redis_client.hgetall(key)
            data['data'] = json.loads(data['data'])
            data['active'] = data['active'] == "True"
            self.logger.info(f"Loaded strategy ID '{strategy_id}' successfully.")
            return data
        except Exception as e:
            self.logger.error(f"Failed to load strategy ID '{strategy_id}': {e}")
            raise

    def list_strategies(self) -> List[Dict]:
        """
        Lists all saved strategies.
        :return: List of dictionaries containing strategy IDs, titles, and activation statuses.
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
        Activates a strategy by setting its active status to True.
        :param strategy_id: The unique ID of the strategy.
        """
        key = f"strategy:{strategy_id}"
        if not self.redis_client.exists(key):
            self.logger.error(f"Strategy with ID '{strategy_id}' does not exist.")
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")
        try:
            self.redis_client.hset(key, "active", "True")
            self.logger.info(f"Activated strategy ID '{strategy_id}'.")
        except Exception as e:
            self.logger.error(f"Failed to activate strategy ID '{strategy_id}': {e}")
            raise

    def deactivate_strategy(self, strategy_id: str):
        """
        Deactivates a strategy by setting its active status to False.
        :param strategy_id: The unique ID of the strategy.
        """
        key = f"strategy:{strategy_id}"
        if not self.redis_client.exists(key):
            self.logger.error(f"Strategy with ID '{strategy_id}' does not exist.")
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")
        try:
            self.redis_client.hset(key, "active", "False")
            self.logger.info(f"Deactivated strategy ID '{strategy_id}'.")
        except Exception as e:
            self.logger.error(f"Failed to deactivate strategy ID '{strategy_id}': {e}")
            raise

    def remove_strategy(self, strategy_id: str):
        """
        Removes a strategy by its unique ID.
        :param strategy_id: The unique ID of the strategy.
        """
        key = f"strategy:{strategy_id}"
        if not self.redis_client.exists(key):
            self.logger.error(f"Strategy with ID '{strategy_id}' does not exist.")
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")
        try:
            self.redis_client.delete(key)
            self.logger.info(f"Removed strategy ID '{strategy_id}' successfully.")
        except Exception as e:
            self.logger.error(f"Failed to remove strategy ID '{strategy_id}': {e}")
            raise

    def get_active_strategies(self) -> List[Dict]:
        """
        Retrieves all active strategies.
        :return: List of dictionaries containing active strategy IDs and data.
        """
        try:
            keys = self.redis_client.keys("strategy:*")
            active_strategies = []
            for key in keys:
                data = self.redis_client.hgetall(key)
                if data['active'] == "True":
                    active_strategies.append({
                        "id": data['id'],
                        "title": data['title'],
                        "data": json.loads(data['data'])
                    })
            self.logger.info("Retrieved all active strategies successfully.")
            return active_strategies
        except Exception as e:
            self.logger.error(f"Failed to retrieve active strategies: {e}")
            raise

    def validate_strategy(self, strategy_data: Dict) -> bool:
        """
        Validates a strategy to ensure all required fields are present.
        :param strategy_data: The strategy data to validate.
        :return: True if valid, False otherwise.
        """
        required_keys = ["strategy_name", "market_type", "assets", "trade_parameters", "conditions", "risk_management"]
        is_valid = all(key in strategy_data and strategy_data[key] for key in required_keys)
        self.logger.debug(f"Strategy validation result: {is_valid}")
        return is_valid
