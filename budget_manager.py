import redis
import threading
import logging
from typing import Dict


class BudgetManager:
    """
    Manages budgets allocated to different strategies with Redis integration.
    """

    def __init__(self, redis_host='localhost', redis_port=6379, redis_db=0):
        self.redis_client = redis.StrictRedis(host=redis_host, port=redis_port, db=redis_db, decode_responses=True)
        self.lock = threading.Lock()
        self.logger = logging.getLogger(self.__class__.__name__)

    def set_budget(self, strategy_name: str, amount: float):
        """
        Sets the budget for a strategy in USDT.
        :param strategy_name: The name of the strategy.
        :param amount: The budget amount in USDT.
        """
        if amount < 0:
            self.logger.error("Budget amount cannot be negative.")
            return
        with self.lock:
            try:
                self.redis_client.hset("budgets", strategy_name, amount)
                self.logger.info(f"Budget for '{strategy_name}' set to {amount} USDT.")
            except Exception as e:
                self.logger.error(f"Failed to set budget for '{strategy_name}': {e}")


    def get_budget(self, strategy_name: str) -> float:
        """
        Retrieves the budget for a strategy.
        :param strategy_name: The name of the strategy.
        :return: The budget amount for the strategy or 0.0 if not found.
        """
        with self.lock:
            try:
                budget = self.redis_client.hget("budgets", strategy_name)
                return float(budget) if budget else 0.0
            except Exception as e:
                self.logger.error(f"Failed to get budget for '{strategy_name}': {e}")
                return 0.0

    def update_budget(self, strategy_name: str, new_amount: float):
        """
        Updates the budget for a strategy.
        :param strategy_name: The name of the strategy.
        :param new_amount: The new budget amount.
        """
        if new_amount < 0:
            self.logger.error("Budget amount cannot be negative.")
            return
        with self.lock:
            try:
                if self.redis_client.hexists("budgets", strategy_name):
                    self.redis_client.hset("budgets", strategy_name, new_amount)
                    self.logger.info(f"Budget for '{strategy_name}' updated to {new_amount}.")
                else:
                    self.logger.error(f"No budget found for strategy '{strategy_name}' to update.")
            except Exception as e:
                self.logger.error(f"Failed to update budget for '{strategy_name}': {e}")

    def remove_budget(self, strategy_name: str):
        """
        Removes the budget for a strategy.
        :param strategy_name: The name of the strategy.
        """
        with self.lock:
            try:
                if self.redis_client.hdel("budgets", strategy_name):
                    self.logger.info(f"Budget for '{strategy_name}' removed.")
                else:
                    self.logger.error(f"No budget found for strategy '{strategy_name}' to remove.")
            except Exception as e:
                self.logger.error(f"Failed to remove budget for '{strategy_name}': {e}")

    def get_all_budgets(self) -> Dict[str, float]:
        """
        Retrieves all budgets for all strategies.
        :return: A dictionary of strategy names and their respective budgets.
        """
        with self.lock:
            try:
                budgets = self.redis_client.hgetall("budgets")
                return {key: float(value) for key, value in budgets.items()}
            except Exception as e:
                self.logger.error(f"Failed to retrieve all budgets: {e}")
                return {}
            

    def edit_strategy(self, strategy_id: str, updates: Dict):
        """
        Allows updating specific parameters of a saved strategy.
        :param strategy_id: The unique ID of the strategy.
        :param updates: A dictionary containing the parameters to update.
        """
        key = f"strategy:{strategy_id}"
        if not self.redis_client.exists(key):
            self.logger.error(f"Strategy with ID '{strategy_id}' does not exist.")
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")
        try:
            current_data = self.redis_client.hgetall(key)
            strategy_data = json.loads(current_data['data'])

            # Update the strategy data with the new parameters
            strategy_data.update(updates)

            # Save the updated strategy
            current_data['data'] = json.dumps(strategy_data)
            self.redis_client.hmset(key, current_data)

            self.logger.info(f"Strategy ID '{strategy_id}' updated successfully.")
        except Exception as e:
            self.logger.error(f"Failed to edit strategy ID '{strategy_id}': {e}")
            raise

    def allocate_budget_dynamically(self, total_budget: float, strategy_weights: Dict[str, float]):
        """
        Dynamically allocates a total budget across strategies based on weights.
        :param total_budget: The total budget to allocate.
        :param strategy_weights: A dictionary of strategy names and their weight factors.
        """
        if total_budget < 0:
            self.logger.error("Total budget cannot be negative.")
            return

        total_weight = sum(strategy_weights.values())
        if total_weight == 0:
            self.logger.error("Total weight must be greater than zero.")
            return

        with self.lock:
            try:
                for strategy_name, weight in strategy_weights.items():
                    allocated_budget = (weight / total_weight) * total_budget
                    self.redis_client.hset("budgets", strategy_name, allocated_budget)
                    self.logger.info(f"Allocated {allocated_budget} to strategy '{strategy_name}' based on weight {weight}.")
            except Exception as e:
                self.logger.error(f"Failed to dynamically allocate budget: {e}")
