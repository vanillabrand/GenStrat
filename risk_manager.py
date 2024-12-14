import logging
import redis
import json
from typing import Dict

class RiskManager:
    """
    Manages risk parameters for trading strategies, ensuring proper risk management rules are applied.
    """

    def __init__(self, redis_host='localhost', redis_port=6379, redis_db=0):
        self.redis_client = redis.StrictRedis(host=redis_host, port=redis_port, db=redis_db, decode_responses=True)
        self.logger = logging.getLogger(self.__class__.__name__)

    def set_risk_parameters(self, strategy_name: str, risk_parameters: Dict):
        """
        Sets the risk parameters for a specific strategy.
        :param strategy_name: The name of the strategy.
        :param risk_parameters: Dictionary containing risk parameters (e.g., stop_loss, take_profit).
        """
        key = f"risk:{strategy_name}"
        try:
            self.redis_client.set(key, json.dumps(risk_parameters))
            self.logger.info(f"Set risk parameters for strategy '{strategy_name}': {risk_parameters}")
        except Exception as e:
            self.logger.error(f"Failed to set risk parameters for strategy '{strategy_name}': {e}")

    def get_risk_parameters(self, strategy_name: str) -> Dict:
        """
        Retrieves the risk parameters for a specific strategy.
        :param strategy_name: The name of the strategy.
        :return: Dictionary containing the risk parameters.
        """
        key = f"risk:{strategy_name}"
        try:
            risk_data = self.redis_client.get(key)
            if risk_data:
                self.logger.info(f"Retrieved risk parameters for strategy '{strategy_name}'.")
                return json.loads(risk_data)
            else:
                self.logger.warning(f"No risk parameters found for strategy '{strategy_name}'.")
                return {}
        except Exception as e:
            self.logger.error(f"Failed to retrieve risk parameters for strategy '{strategy_name}': {e}")
            return {}

    def update_risk_parameters(self, strategy_name: str, updated_parameters: Dict):
        """
        Updates specific risk parameters for a strategy.
        :param strategy_name: The name of the strategy.
        :param updated_parameters: Dictionary containing updated risk parameters.
        """
        key = f"risk:{strategy_name}"
        try:
            existing_parameters = self.get_risk_parameters(strategy_name)
            existing_parameters.update(updated_parameters)
            self.redis_client.set(key, json.dumps(existing_parameters))
            self.logger.info(f"Updated risk parameters for strategy '{strategy_name}': {updated_parameters}")
        except Exception as e:
            self.logger.error(f"Failed to update risk parameters for strategy '{strategy_name}': {e}")

    def delete_risk_parameters(self, strategy_name: str):
        """
        Deletes the risk parameters for a specific strategy.
        :param strategy_name: The name of the strategy.
        """
        key = f"risk:{strategy_name}"
        try:
            self.redis_client.delete(key)
            self.logger.info(f"Deleted risk parameters for strategy '{strategy_name}'.")
        except Exception as e:
            self.logger.error(f"Failed to delete risk parameters for strategy '{strategy_name}': {e}")

    def validate_risk_parameters(self, risk_parameters: Dict) -> bool:
        """
        Validates risk parameters to ensure they meet predefined rules.
        :param risk_parameters: Dictionary containing risk parameters.
        :return: Boolean indicating whether the parameters are valid.
        """
        try:
            stop_loss = risk_parameters.get('stop_loss', None)
            take_profit = risk_parameters.get('take_profit', None)
            trailing_stop = risk_parameters.get('trailing_stop_loss', None)

            if stop_loss is not None and (stop_loss <= 0 or stop_loss >= 100):
                self.logger.error("Invalid stop_loss value. Must be between 0 and 100.")
                return False

            if take_profit is not None and (take_profit <= 0 or take_profit >= 100):
                self.logger.error("Invalid take_profit value. Must be between 0 and 100.")
                return False

            if trailing_stop is not None and (trailing_stop <= 0 or trailing_stop >= 100):
                self.logger.error("Invalid trailing_stop_loss value. Must be between 0 and 100.")
                return False

            self.logger.info("Risk parameters are valid.")
            return True
        except Exception as e:
            self.logger.error(f"Error validating risk parameters: {e}")
            return False
