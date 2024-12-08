# budget_manager.py

import threading
import logging
from typing import Dict


class BudgetManager:
    """
    Manages budgets allocated to different strategies.
    """

    def __init__(self):
        self.budgets = {}  # key: strategy_name, value: budget amount
        self.lock = threading.Lock()
        self.logger = logging.getLogger(self.__class__.__name__)

    def set_budget(self, strategy_name: str, amount: float):
        """
        Sets the budget for a strategy.
        """
        if amount < 0:
            self.logger.error("Budget amount cannot be negative.")
            return
        with self.lock:
            self.budgets[strategy_name] = amount
            self.logger.info(f"Budget for '{strategy_name}' set to {amount}.")

    def get_budget(self, strategy_name: str) -> float:
        """
        Retrieves the budget for a strategy.
        """
        with self.lock:
            return self.budgets.get(strategy_name, 0.0)

    def update_budget(self, strategy_name: str, new_amount: float):
        """
        Updates the budget for a strategy.
        """
        if new_amount < 0:
            self.logger.error("Budget amount cannot be negative.")
            return
        with self.lock:
            self.budgets[strategy_name] = new_amount
            self.logger.info(f"Budget for '{strategy_name}' updated to {new_amount}.")

    def remove_budget(self, strategy_name: str):
        """
        Removes the budget for a strategy.
        """
        with self.lock:
            if strategy_name in self.budgets:
                del self.budgets[strategy_name]
                self.logger.info(f"Budget for '{strategy_name}' removed.")
            else:
                self.logger.error(f"No budget found for strategy '{strategy_name}'.")
