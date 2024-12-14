import logging
from strategy_manager import StrategyManager
from budget_manager import BudgetManager
from performance_manager import PerformanceManager
from backtester import Backtester
from strategy_interpreter import StrategyInterpreter


class UserInterface:
    """
    Handles terminal-based interaction for managing trading strategies, budgets, risk levels, and performance metrics.
    """

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.strategy_manager = StrategyManager()
        self.budget_manager = BudgetManager()
        self.performance_manager = PerformanceManager()
        self.backtester = Backtester()

    def main(self):
        """
        Main loop for the user interface.
        """
        while True:
            print("\n--- Main Menu ---")
            print("1. Create New Strategy")
            print("2. Load Strategy")
            print("3. List Strategies")
            print("4. Assign Budget")
            print("5. View Performance Metrics")
            print("6. Run Backtests")
            print("7. Exit")

            choice = input("Enter your choice: ").strip()

            if choice == "7":
                self.exit_program()
                break  # Breaks out of the loop when exiting
            else:
                self.handle_menu_choice(choice)

    def handle_menu_choice(self, choice):
        """
        Handles user input for the main menu.
        """
        menu_options = {
            "1": self.create_new_strategy,
            "2": self.load_strategy,
            "3": self.list_strategies,
            "4": self.assign_budget,
            "5": self.view_performance_metrics,
            "6": self.run_backtests,
        }

        action = menu_options.get(choice)
        if action:
            action()
        else:
            print("Invalid choice. Please try again.")

    def create_new_strategy(self):
        """
        Prompts the user to create a new strategy, interprets it using the StrategyInterpreter, and saves it.
        """
        try:
            title = input("Enter the strategy title: ").strip()
            description = input("Enter the strategy description: ").strip()

            interpreter = StrategyInterpreter()
            strategy_json = interpreter.interpret(description)

            self.strategy_manager.save_strategy(title, description, strategy_json)
            print(f"Strategy '{title}' created successfully.")
        except Exception as e:
            self.logger.error(f"Failed to create a new strategy: {e}")
            print(f"Error: {e}")

    def load_strategy(self):
        """
        Allows the user to load and view a saved strategy.
        """
        try:
            strategy_id = input("Enter the strategy ID to load: ").strip()
            strategy = self.strategy_manager.load_strategy(strategy_id)
            if strategy:
                print("\n--- Strategy Details ---")
                print(f"ID: {strategy_id}")
                print(f"Title: {strategy['title']}")
                print(f"Description: {strategy['description']}")
                print(f"Data: {strategy['data']}")
            else:
                print(f"No strategy found with ID: {strategy_id}")
        except Exception as e:
            self.logger.error(f"Failed to load strategy: {e}")
            print(f"Error: {e}")

    def list_strategies(self):
        """
        Lists all saved strategies.
        """
        try:
            strategies = self.strategy_manager.list_strategies()
            print("\n--- Strategies ---")
            for strategy in strategies:
                print(f"ID: {strategy['id']}, Title: {strategy['title']}, Active: {strategy['active']}")
        except Exception as e:
            self.logger.error(f"Failed to list strategies: {e}")
            print(f"Error: {e}")

    def assign_budget(self):
        """
        Assigns a budget to a strategy.
        """
        try:
            strategy_id = input("Enter the strategy ID: ").strip()
            amount = float(input("Enter the budget amount: "))
            self.budget_manager.set_budget(strategy_id, amount)
            print(f"Budget of {amount} assigned to strategy '{strategy_id}'.")
        except Exception as e:
            self.logger.error(f"Failed to assign budget: {e}")
            print(f"Error: {e}")

    def view_performance_metrics(self):
        """
        Displays performance metrics for a strategy.
        """
        try:
            strategy_id = input("Enter the strategy ID: ").strip()
            metrics = self.performance_manager.calculate_summary(strategy_id)
            print("\n--- Performance Metrics ---")
            for key, value in metrics.items():
                print(f"{key}: {value}")
        except Exception as e:
            self.logger.error(f"Failed to view performance metrics: {e}")
            print(f"Error: {e}")

    def run_backtests(self):
        """
        Runs backtests for a selected strategy.
        """
        try:
            strategy_id = input("Enter the strategy ID: ").strip()
            historical_data_path = input("Enter the path to historical data (CSV): ").strip()

            from pandas import read_csv
            historical_data = read_csv(historical_data_path)
            strategy = self.strategy_manager.load_strategy(strategy_id)

            self.backtester.run_backtest(strategy, historical_data)
            print(f"Backtest completed for strategy '{strategy_id}'.")
        except Exception as e:
            self.logger.error(f"Failed to run backtest: {e}")
            print(f"Error: {e}")

    def exit_program(self):
        """
        Exits the program.
        """
        print("Exiting... Goodbye!")
