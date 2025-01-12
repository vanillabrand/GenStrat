import redis
import threading
import logging
from typing import Dict
import asyncio


class BudgetManager:
    """
    Manages budgets allocated to different strategies with Redis integration.
    Ensures dynamic allocation, fallback adjustments, and balance validation against exchange funds.
    """

    def __init__(self, redis_host='localhost', redis_port=6379, redis_db=0, exchange=None):
        self.redis_client = redis.StrictRedis(
            host=redis_host, port=redis_port, db=redis_db, decode_responses=True
        )
        self.lock = threading.Lock()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.exchange = exchange  # Integration with exchange for balance validation

    ### --- Budget Management ---

    def set_budget(self, strategy_name: str, amount: float):
        """
        Sets the budget for a strategy.
        """
        if amount < 0:
            self.logger.error("Budget amount cannot be negative.")
            return
        with self.lock:
            try:
                self.redis_client.hset("budgets", strategy_name, amount)
                self.logger.info(f"Budget for '{strategy_name}' set to {amount:.2f}.")
            except Exception as e:
                self.logger.error(f"Failed to set budget for '{strategy_name}': {e}")

    def get_budget(self, strategy_name: str) -> float:
        """
        Retrieves the budget for a strategy.
        """
        with self.lock:
            try:
                budget = self.redis_client.hget("budgets", strategy_name)
                return float(budget) if budget else 0.0
            except Exception as e:
                self.logger.error(f"Failed to get budget for '{strategy_name}': {e}")
                return 0.0

    def update_budget(self, strategy_name: str, amount_spent: float):
        """
        Deducts the spent amount from a strategy's budget.
        """
        with self.lock:
            try:
                current_budget = self.get_budget(strategy_name)
                if current_budget < amount_spent:
                    self.logger.warning(
                        f"Budget for '{strategy_name}' insufficient. Current: {current_budget:.2f}, Needed: {amount_spent:.2f}."
                    )
                    return False
                new_budget = current_budget - amount_spent
                self.redis_client.hset("budgets", strategy_name, new_budget)
                self.logger.info(
                    f"Deducted {amount_spent:.2f} from budget of '{strategy_name}'. New budget: {new_budget:.2f}."
                )
                return True
            except Exception as e:
                self.logger.error(f"Failed to update budget for '{strategy_name}': {e}")
                return False

    def return_budget(self, strategy_name: str, amount: float):
        """
        Returns unspent budget back to the strategy's available funds.
        """
        with self.lock:
            try:
                current_budget = self.get_budget(strategy_name)
                new_budget = current_budget + amount
                self.redis_client.hset("budgets", strategy_name, new_budget)
                self.logger.info(
                    f"Returned {amount:.2f} USDT to strategy '{strategy_name}'. New budget: {new_budget:.2f}."
                )
            except Exception as e:
                self.logger.error(f"Failed to return budget for '{strategy_name}': {e}")

    ### --- Dynamic Budget Allocation ---

    def allocate_budget_dynamically(self, total_budget: float, strategy_weights: Dict[str, float]):
        """
        Dynamically allocates a total budget across strategies based on weights.
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
                    self.logger.info(
                        f"Allocated {allocated_budget:.2f} to strategy '{strategy_name}' based on weight {weight}."
                    )
            except Exception as e:
                self.logger.error(f"Failed to dynamically allocate budget: {e}")

    ### --- Exchange Balance Validation ---

    async def get_exchange_balance(self, asset: str) -> float:
        """
        Retrieves the available balance of an asset from the exchange.
        """
        try:
            if self.exchange:
                balance = await self.exchange.fetch_balance()
                return balance["free"].get(asset, 0.0)  # 'free' represents available balance
            else:
                self.logger.warning("Exchange instance not set. Returning 0 balance.")
                return 0.0
        except Exception as e:
            self.logger.error(f"Failed to fetch balance for '{asset}': {e}")
            return 0.0

    async def validate_budget_against_exchange(self, strategy_name: str, asset: str):
        """
        Ensures the budget for a strategy does not exceed the available exchange balance.
        """
        with self.lock:
            try:
                strategy_budget = self.get_budget(strategy_name)
                exchange_balance = await self.get_exchange_balance(asset)
                if strategy_budget > exchange_balance:
                    self.logger.warning(
                        f"Budget for '{strategy_name}' exceeds exchange balance for '{asset}'. "
                        f"Reducing budget to {exchange_balance:.2f}."
                    )
                    self.set_budget(strategy_name, exchange_balance)
            except Exception as e:
                self.logger.error(f"Failed to validate budget for '{strategy_name}' against exchange balance: {e}")

    ### --- Retrieval Methods ---

    def get_all_budgets(self) -> Dict[str, float]:
        """
        Retrieves all budgets for all strategies.
        """
        with self.lock:
            try:
                budgets = self.redis_client.hgetall("budgets")
                return {key: float(value) for key, value in budgets.items()}
            except Exception as e:
                self.logger.error(f"Failed to retrieve all budgets: {e}")
                return {}

    def remove_budget(self, strategy_name: str):
        """
        Removes the budget for a strategy.
        """
        with self.lock:
            try:
                if self.redis_client.hdel("budgets", strategy_name):
                    self.logger.info(f"Budget for '{strategy_name}' removed.")
                else:
                    self.logger.error(f"No budget found for strategy '{strategy_name}' to remove.")
            except Exception as e:
                self.logger.error(f"Failed to remove budget for '{strategy_name}': {e}")
