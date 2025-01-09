import redis
import json
import uuid
import logging
from typing import Dict, List, Union


class StrategyManager:
    """
    Manages the storage, retrieval, editing, activation, and removal of trading strategies.
    Each strategy is assigned a unique ID and a user-defined title.
    Integrates with TradeManager to handle trade lifecycle.
    """

    def __init__(self, trade_manager=None, market_monitor=None, redis_host='localhost', redis_port=6379, redis_db=0):
        self.redis_client = redis.StrictRedis(
            host=redis_host, port=redis_port, db=redis_db, decode_responses=True
        )
        self.logger = logging.getLogger(self.__class__.__name__)
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        self.trade_manager = trade_manager  # Dependency for managing trades
        self.market_monitor = market_monitor  # Dependency for monitoring market conditions

    def generate_unique_id(self) -> str:
        """Generates a unique ID for a strategy."""
        return str(uuid.uuid4())

    def set_monitoring(self, market_monitor):
        """
        Sets the MarketMonitor instance.
        """
        self.market_monitor = market_monitor

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
        :param strategy_data: JSON-serializable dictionary containing the entire strategy details, e.g.:
            {
                'strategy_name': 'High Risk Advanced Sniper',
                'strategy_rationale': '...', 
                'market_type': 'futures',
                'assets': [...],
                'trade_parameters': {...},
                'conditions': {...},
                'risk_management': {...}
            }
        :return: The unique ID of the saved strategy.
        """
        if not isinstance(strategy_data, dict):
            raise ValueError("Strategy data must be a dictionary.")

        strategy_id = self.generate_unique_id()
        key = f"strategy:{strategy_id}"

        # Store top-level metadata, then store the entire 'strategy_data' dict as JSON under 'data'.
        strategy_record = {
            "id": strategy_id,
            "title": title,
            "description": description,
            "data": json.dumps(strategy_data),  # store the entire structure unchanged
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
        Updates an existing strategy's fields, ensuring the 'data' section is properly merged.
        :param strategy_input: Strategy ID or dictionary containing the ID.
        :param updates: Dictionary of fields to update.
        """
        strategy_id = self.validate_strategy_id(strategy_input)
        key = f"strategy:{strategy_id}"

        if not self.redis_client.exists(key):
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")

        try:
            # Load existing strategy
            existing_data = self.redis_client.hgetall(key)
            
            if not existing_data:
                raise ValueError(f"Strategy with ID '{strategy_id}' not found.")

            # Update general fields
            for field, value in updates.items():
                if field != 'data':
                    existing_data[field] = value
            
            # Merge nested 'data' dictionary if provided
            if 'data' in updates:
                strategy_data = json.loads(existing_data.get('data', '{}'))
                strategy_data.update(updates['data'])
                existing_data['data'] = json.dumps(strategy_data)

            # Save updated strategy back to Redis
            self.redis_client.hset(key, mapping=existing_data)
            self.logger.info(f"Strategy ID '{strategy_id}' updated successfully.")
        except Exception as e:
            self.logger.error(f"Failed to update strategy ID '{strategy_id}': {e}")
            raise

    async def activate_strategy(self, strategy_input: Union[str, Dict]):
        """
        Activates a strategy for trading and monitoring.
        :param strategy_input: Strategy ID or dictionary containing the ID.
        """
        strategy_id = self.validate_strategy_id(strategy_input)
        key = f"strategy:{strategy_id}"

        if not self.redis_client.exists(key):
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")

        try:
            self.redis_client.hset(key, "active", "True")
            strategy = self.load_strategy(strategy_id)

            if self.market_monitor:
                await self.market_monitor.activate_monitoring(strategy)

            self.logger.info(f"Activated strategy ID '{strategy_id}'.")
        except Exception as e:
            self.logger.error(f"Failed to activate strategy ID '{strategy_id}': {e}")
            raise

    async def deactivate_strategy(self, strategy_input: Union[str, Dict], force_close: bool = False):
        """
        Deactivates a strategy, with an option to force-close active trades.
        :param strategy_input: Strategy ID or dictionary containing the ID.
        :param force_close: If True, close all active trades for this strategy.
        """
        strategy_id = self.validate_strategy_id(strategy_input)
        key = f"strategy:{strategy_id}"

        if not self.redis_client.exists(key):
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")

        try:
            self.redis_client.hset(key, "active", "False")

            if self.market_monitor:
                await self.market_monitor.deactivate_monitoring(strategy_id)

            if force_close:
                active_trades = self.trade_manager.get_active_trades()
                for trade in active_trades:
                    if trade["strategy_name"] == strategy_id:
                        await self.trade_executor.close_trade(trade["trade_id"], "strategy_deactivation")

            self.logger.info(f"Deactivated strategy ID '{strategy_id}'. Force close: {force_close}.")
        except Exception as e:
            self.logger.error(f"Failed to deactivate strategy ID '{strategy_id}': {e}")
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
                    self.logger.info(f"Found strategies: {data}")
                    strategy = {
                        "id": data.get('id', 'N/A'),
                        "title": data.get('title', 'N/A'),
                        "active": data.get('active', 'False') == "True",
                        "description": data.get('description', 'N/A'),
                        "assets": json.loads(data['data']).get('assets', []) if 'data' in data else [],
                    }
                    strategies.append(strategy)
                return strategies
            except Exception as e:
                self.logger.error(f"Failed to list strategies: {e}")
                return []
            
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

    async def activate_strategy(self, strategy_input: Union[str, Dict]):
        strategy_id = self.validate_strategy_id(strategy_input)
        key = f"strategy:{strategy_id}"

        if not self.redis_client.exists(key):
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")

        try:
            self.redis_client.hset(key, "active", "True")
            strategy = self.load_strategy(strategy_id)
            if self.market_monitor:
                await self.market_monitor.activate_monitoring(strategy)
            self.logger.info(f"Activated strategy ID '{strategy_id}'.")
        except Exception as e:
            self.logger.error(f"Failed to activate strategy ID '{strategy_id}': {e}")
            raise

    def edit_strategy(self, strategy_input: Union[str, Dict], new_data: Dict):
            """
            Edits an existing strategy, replacing its data.
            :param strategy_input: Strategy ID or dictionary containing the ID.
            :param new_data: New strategy data to replace the old one.
            """
            strategy_id = self.validate_strategy_id(strategy_input)
            key = f"strategy:{strategy_id}"

            if not self.redis_client.exists(key):
                raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")

            if not isinstance(new_data, dict):
                raise ValueError("New strategy data must be a dictionary.")

            try:
                existing_data = self.redis_client.hgetall(key)
                existing_data["data"] = json.dumps(new_data)

                self.redis_client.hset(key, mapping=existing_data)
                self.logger.info(f"Strategy ID '{strategy_id}' edited successfully.")
            except Exception as e:
                self.logger.error(f"Failed to edit strategy ID '{strategy_id}': {e}")
                raise