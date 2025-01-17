import redis
import json
import uuid
import logging
from typing import Dict, List, Union


class StrategyManager:
    """
    Manages the storage, retrieval, editing, activation, and removal of trading strategies.
    Each strategy is assigned a unique ID and a user-defined title.
    Integrates with TradeManager and MarketMonitor for trade lifecycle and market condition monitoring.
    """

    def __init__(self, trade_manager=None, market_monitor=None, redis_host='localhost', redis_port=6379, redis_db=0):
        self.redis_client = redis.StrictRedis(
            host=redis_host, port=redis_port, db=redis_db, decode_responses=True
        )
        self.logger = logging.getLogger(self.__class__.__name__)
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        self.trade_manager = trade_manager
        self.market_monitor = market_monitor

    def set_monitoring(self, market_monitor):
        """
        Sets the MarketMonitor instance for strategy monitoring.
        """
        self.market_monitor = market_monitor

    def generate_unique_id(self) -> str:
        """Generates a unique ID for a strategy."""
        return str(uuid.uuid4())

    ### --- Validation Methods ---

    def validate_strategy_id(self, strategy_input: Union[str, Dict]) -> str:
        """
        Validates and extracts the strategy ID.
        """
        if isinstance(strategy_input, dict):
            strategy_id = strategy_input.get('id')
        else:
            strategy_id = strategy_input

        if not strategy_id:
            raise ValueError("Strategy ID cannot be None or empty.")
        return str(strategy_id)

    def validate_strategy_data(self, strategy_data: Dict):
        """
        Validates strategy data for required fields and structure.
        """
        required_fields = ['strategy_name', 'market_type', 'assets', 'trade_parameters', 'conditions', 'risk_management']
        for field in required_fields:
            if field not in strategy_data:
                raise ValueError(f"Strategy data must include '{field}'.")

        # Validate risk management
        risk_management = strategy_data.get('risk_management', {})
        if not isinstance(risk_management, dict) or 'stop_loss' not in risk_management or 'take_profit' not in risk_management:
            raise ValueError("Risk management must include 'stop_loss' and 'take_profit'.")

        if not (0 < risk_management['stop_loss'] < 100):
            raise ValueError("Stop-loss must be between 0 and 100%.")
        if not (0 < risk_management['take_profit'] < 500):
            raise ValueError("Take-profit must be between 0 and 500%.")

        # Validate trade parameters
        trade_parameters = strategy_data.get('trade_parameters', {})
        if not isinstance(trade_parameters, dict) or 'leverage' not in trade_parameters:
            raise ValueError("Trade parameters must include 'leverage'.")

        if not (1 <= trade_parameters['leverage'] <= 100):
            raise ValueError("Leverage must be between 1x and 100x.")

    ### --- Strategy Management ---

    def save_strategy(self, title: str, description: str, strategy_data: Dict) -> str:
        """
        Saves a new strategy to Redis.
        """
        self.validate_strategy_data(strategy_data)

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

    def list_strategies(self) -> List[Dict]:
        """
        Lists all saved strategies in Redis.
        """
        try:
            keys = self.redis_client.keys("strategy:*")
            strategies = []
            for key in keys:
                data = self.redis_client.hgetall(key)
                strategies.append({
                    "id": data.get('id', 'N/A'),
                    "title": data.get('title', 'N/A'),
                    "description": data.get('description', 'N/A'),
                    "active": data.get('active', 'False') == "True",
                    "market_type": json.loads(data['data']).get('market_type', 'N/A') if 'data' in data else 'N/A',
                    "assets": json.loads(data['data']).get('assets', []) if 'data' in data else [],
                })
            return strategies
        except Exception as e:
            self.logger.error(f"Failed to list strategies: {e}")
            return []

    def list_active_strategies(self) -> List[Dict]:
        """
        Lists all active strategies.
        """
        return [s for s in self.list_strategies() if s['active']]

    def activate_strategy(self, strategy_id: str):
        """
        Activates a strategy by setting its 'active' flag to True.
        """
        key = f"strategy:{strategy_id}"
        if not self.redis_client.exists(key):
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")
        try:
            self.redis_client.hset(key, "active", "True")
            self.logger.info(f"Strategy '{strategy_id}' activated successfully.")
        except Exception as e:
            self.logger.error(f"Failed to activate strategy '{strategy_id}': {e}")
            raise

    def deactivate_strategy(self, strategy_id: str):
        """
        Deactivates a strategy by setting its 'active' flag to False.
        """
        key = f"strategy:{strategy_id}"
        if not self.redis_client.exists(key):
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")
        try:
            self.redis_client.hset(key, "active", "False")
            self.logger.info(f"Strategy '{strategy_id}' deactivated successfully.")
        except Exception as e:
            self.logger.error(f"Failed to deactivate strategy '{strategy_id}': {e}")
            raise

    def load_strategy(self, strategy_input: Union[str, Dict]) -> Dict:
        """
        Loads a strategy from Redis.
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

    def remove_strategy(self, strategy_id: str):
        """
        Removes a strategy from Redis.
        """
        key = f"strategy:{strategy_id}"
        if not self.redis_client.exists(key):
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")
        try:
            self.redis_client.delete(key)
            self.logger.info(f"Strategy '{strategy_id}' removed successfully.")
        except Exception as e:
            self.logger.error(f"Failed to remove strategy '{strategy_id}': {e}")
            raise

    def get_strategy_data(self, strategy_id: str) -> Dict:
            """
            Retrieves the strategy data for the given strategy ID from Redis.
            :param strategy_id: The unique ID of the strategy.
            :return: A dictionary containing strategy details.
            """
            try:
                strategy_data = self.redis_client.hgetall(f"strategy:{strategy_id}")
                if not strategy_data:
                    self.logger.warning(f"No data found for strategy ID '{strategy_id}'.")
                    return {}
                
                # Deserialize fields if necessary
                strategy_data["assets"] = strategy_data.get("assets", "").split(",")  # Example: "BTC/USDT,ETH/USDT"
                strategy_data["conditions"] = eval(strategy_data.get("conditions", "{}"))  # Convert string to dict
                return strategy_data
            except Exception as e:
                self.logger.error(f"Failed to get strategy data for '{strategy_id}': {e}")
                return {}
            
            
    def edit_strategy(self, strategy_id: str, updates: Dict):
        """
        Edits an existing strategy in Redis.
        :param strategy_id: The unique ID of the strategy to edit.
        :param updates: A dictionary containing the fields to update.
        """
        key = f"strategy:{strategy_id}"

        if not self.redis_client.exists(key):
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")

        try:
            # Fetch the existing strategy
            current_strategy = self.redis_client.hgetall(key)
            if not current_strategy:
                raise ValueError(f"Strategy with ID '{strategy_id}' is empty or corrupted.")

            # Deserialize the existing strategy data
            current_data = json.loads(current_strategy.get("data", "{}"))

            # Apply updates to the strategy data
            updated_data = {**current_data, **updates.get("data", {})}
            self.validate_strategy_data(updated_data)  # Validate updated data

            # Update Redis with the new data
            updated_strategy = {
                "id": strategy_id,
                "title": updates.get("title", current_strategy.get("title")),
                "description": updates.get("description", current_strategy.get("description")),
                "data": json.dumps(updated_data),
                "active": current_strategy.get("active", "False"),  # Preserve active status
            }

            # Save the updated strategy back to Redis
            self.redis_client.hset(key, mapping=updated_strategy)
            self.logger.info(f"Strategy '{strategy_id}' updated successfully.")
        except Exception as e:
            self.logger.error(f"Failed to edit strategy '{strategy_id}': {e}")
            raise
