import redis
import json
import uuid
import logging
from typing import Dict, List, Union


class StrategyManager:
    """
    Manages the storage, retrieval, editing, and activation of trading strategies.
    Each strategy is assigned a unique ID and a user-defined title.
    """

    def __init__(self, redis_host='localhost', redis_port=6379, redis_db=0):
        self.redis_client = redis.StrictRedis(
            host=redis_host, port=redis_port, db=redis_db, decode_responses=True
        )
        self.logger = logging.getLogger(self.__class__.__name__)

    def generate_unique_id(self) -> str:
        """Generates a unique ID for a strategy."""
        return str(uuid.uuid4())

    def validate_strategy_id(self, strategy_input: Union[str, Dict]) -> str:
        """
        Validates and extracts the strategy ID, converting it to a string if necessary.
        :param strategy_input: Strategy ID or dictionary containing the ID.
        :return: Validated strategy ID as a string.
        """
        if isinstance(strategy_input, dict):
            strategy_id = strategy_input.get('id')
        else:
            strategy_id = strategy_input

        if not strategy_id:
            raise ValueError("Strategy ID cannot be None or empty.")
        return str(strategy_id)

    def save_strategy(self, title: str, description: str, strategy_data: Dict) -> str:
        """
        Saves a new strategy to Redis.
        :param title: Title of the strategy.
        :param description: Description of the strategy.
        :param strategy_data: JSON-serializable dictionary containing strategy details.
        :return: The unique ID of the saved strategy.
        """
        strategy_id = self.generate_unique_id()
        key = f"strategy:{strategy_id}"
        strategy_record = {
            "id": strategy_id,
            "title": title,
            "description": description,
            "data": json.dumps(strategy_data),
            "active": "False",
        }

        try:
            self.redis_client.hset(key, mapping=strategy_record)
            self.logger.info(f"Strategy '{title}' with ID '{strategy_id}' saved successfully.")
            return strategy_id
        except Exception as e:
            self.logger.error(f"Failed to save strategy '{title}': {e}")
            raise

    def update_strategy(self, strategy_input: Union[str, Dict], updates: Dict):
        """
        Updates an existing strategy's fields.
        :param strategy_input: Strategy ID or dictionary containing the ID.
        :param updates: Dictionary of fields to update.
        """
        strategy_id = self.validate_strategy_id(strategy_input)
        key = f"strategy:{strategy_id}"

        if not self.redis_client.exists(key):
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")

        try:
            existing_data = self.redis_client.hgetall(key)
            if 'data' in updates:
                merged_data = json.loads(existing_data['data'])
                merged_data.update(updates.pop('data'))
                updates['data'] = json.dumps(merged_data)

            self.redis_client.hset(key, mapping=updates)
            self.logger.info(f"Strategy ID '{strategy_id}' updated successfully.")
        except Exception as e:
            self.logger.error(f"Failed to update strategy ID '{strategy_id}': {e}")
            raise

    def edit_strategy(self, strategy_input: Union[str, Dict], new_title: str = None,
                      new_description: str = None, new_data: Dict = None):
        """
        Edits a strategy's details.
        :param strategy_input: Strategy ID or dictionary containing the ID.
        :param new_title: Updated title for the strategy.
        :param new_description: Updated description for the strategy.
        :param new_data: Updated strategy data.
        """
        updates = {}
        if new_title:
            updates['title'] = new_title
        if new_description:
            updates['description'] = new_description
        if new_data:
            updates['data'] = new_data

        self.update_strategy(strategy_input, updates)

    def load_strategy(self, strategy_input: Union[str, Dict]) -> Dict:
        """
        Loads a strategy from Redis.
        :param strategy_input: Strategy ID or dictionary containing the ID.
        :return: A dictionary with the strategy details.
        """
        strategy_id = self.validate_strategy_id(strategy_input)
        key = f"strategy:{strategy_id}"

        if not self.redis_client.exists(key):
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")

        try:
            strategy = self.redis_client.hgetall(key)
            strategy['data'] = json.loads(strategy['data'])
            strategy['active'] = strategy['active'] == "True"
            return strategy
        except Exception as e:
            self.logger.error(f"Failed to load strategy ID '{strategy_id}': {e}")
            raise

    def list_strategies(self) -> List[Dict]:
        """
        Lists all saved strategies.
        :return: A list of dictionaries with strategy details.
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
            return strategies
        except Exception as e:
            self.logger.error(f"Failed to list strategies: {e}")
            raise

    def activate_strategy(self, strategy_input: Union[str, Dict]):
        """
        Activates a strategy for trading.
        :param strategy_input: Strategy ID or dictionary containing the ID.
        """
        strategy_id = self.validate_strategy_id(strategy_input)
        key = f"strategy:{strategy_id}"

        if not self.redis_client.exists(key):
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")

        try:
            self.redis_client.hset(key, "active", "True")
            self.logger.info(f"Activated strategy ID '{strategy_id}'.")
        except Exception as e:
            self.logger.error(f"Failed to activate strategy ID '{strategy_id}': {e}")
            raise

    def deactivate_strategy(self, strategy_input: Union[str, Dict]):
        """
        Deactivates a strategy.
        :param strategy_input: Strategy ID or dictionary containing the ID.
        """
        strategy_id = self.validate_strategy_id(strategy_input)
        key = f"strategy:{strategy_id}"

        if not self.redis_client.exists(key):
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")

        try:
            self.redis_client.hset(key, "active", "False")
            self.logger.info(f"Deactivated strategy ID '{strategy_id}'.")
        except Exception as e:
            self.logger.error(f"Failed to deactivate strategy ID '{strategy_id}': {e}")
            raise
        
    def remove_strategy(self, strategy_input: Union[str, Dict]) -> None:
        """
        Removes a strategy from Redis.
        :param strategy_input: Strategy ID or dictionary containing the ID.
        """
        strategy_id = self.validate_strategy_id(strategy_input)
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

    def remove_strategy(self, strategy_input: Union[str, Dict]):
        """
        Removes a strategy from Redis.
        :param strategy_input: Strategy ID or dictionary containing the ID.
        """
        strategy_id = self.validate_strategy_id(strategy_input)
        key = f"strategy:{strategy_id}"

        if not self.redis_client.exists(key):
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")

        try:
            self.redis_client.delete(key)
            self.logger.info(f"Removed strategy ID '{strategy_id}' successfully.")
        except Exception as e:
            self.logger.error(f"Failed to remove strategy ID '{strategy_id}': {e}")
            raise
