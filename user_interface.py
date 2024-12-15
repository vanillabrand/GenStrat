import logging
from strategy_manager import StrategyManager
from budget_manager import BudgetManager
from performance_manager import PerformanceManager
from backtester import Backtester
from strategy_interpreter import StrategyInterpreter
from config import Config
from synthetic_data_generator import generate_synthetic_data  # Assuming a separate module for synthetic data


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
        self.strategy_interpreter = StrategyInterpreter(Config.OPENAI_API_KEY)

    def main(self):
        """
        Main loop for the user interface.
        """
        while True:
            print("\n--- Main Menu ---")
            print("1. Create New Strategy")
            print("2. Edit Existing Strategy")
            print("3. Activate a Strategy")
            print("4. List Strategies")
            print("5. Assign Budget")
            print("6. View Performance Metrics")
            print("7. Run Backtests")
            print("8. Exit")

            choice = input("Enter your choice: ").strip()

            if choice == "8":
                self.exit_program()
                break
            else:
                self.handle_menu_choice(choice)

    def handle_menu_choice(self, choice):
        """
        Handles user input for the main menu.
        """
        menu_options = {
            "1": self.create_new_strategy,
            "2": self.edit_strategy,
            "3": self.activate_strategy,
            "4": self.list_strategies,
            "5": self.assign_budget,
            "6": self.view_performance_metrics,
            "7": self.run_backtests,
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

            strategy_json = self.strategy_interpreter.interpret(description)
            self.strategy_manager.save_strategy(title, description, strategy_json)
            print(f"Strategy '{title}' created successfully.")
        except Exception as e:
            self.logger.error(f"Failed to create a new strategy: {e}")
            print(f"Error: {e}")

    def edit_strategy(self):
        """
        Prompts the user to edit an existing strategy interactively.
        """
        try:
            strategy = self.strategy_manager.list_strategies_for_selection()
            strategy_id = strategy['id']
            current_data = self.strategy_manager.load_strategy(strategy_id)

            print("\n--- Editing Strategy ---")
            print(f"Current Title: {current_data['title']}")
            print(f"Current Description: {current_data['description']}")
            print("Editable Parameters:")

            updates = {}
            for key, value in current_data['data'].items():
                new_value = input(f"{key} (current: {value}): ").strip()
                if new_value:
                    updates[key] = new_value

            self.strategy_manager.edit_strategy(strategy_id, updates)
            print("Strategy updated successfully.")
        except Exception as e:
            self.logger.error(f"Failed to edit strategy: {e}")
            print(f"Error: {e}")

    def activate_strategy(self):
        """
        Activates a strategy and ensures it's monitored by the application.
        """
        try:
            strategy = self.strategy_manager.list_strategies_for_selection()
            strategy_id = strategy['id']
            self.strategy_manager.activate_strategy(strategy_id)
            print(f"Strategy '{strategy['title']}' activated successfully.")
        except Exception as e:
            self.logger.error(f"Failed to activate strategy: {e}")
            print(f"Error: {e}")

    def list_strategies(self):
        """
        Lists all saved strategies in a user-friendly format.
        """
        try:
            strategies = self.strategy_manager.list_strategies()
            print("\n--- Strategies ---")
            for idx, strategy in enumerate(strategies, start=1):
                print(f"{idx}. Title: {strategy['title']} (ID: {strategy['id']}, Active: {strategy['active']})")
        except Exception as e:
            self.logger.error(f"Failed to list strategies: {e}")
            print(f"Error: {e}")

    def assign_budget(self):
        """
        Assigns a budget to a strategy in USDT.
        """
        try:
            strategy = self.strategy_manager.list_strategies_for_selection()
            strategy_name = strategy['title']
            amount = float(input("Enter the budget amount in USDT: "))
            self.budget_manager.set_budget(strategy_name, amount)
            print(f"Budget of {amount} USDT assigned to strategy '{strategy_name}'.")
        except Exception as e:
            self.logger.error(f"Failed to assign budget: {e}")
            print(f"Error: {e}")

    def view_performance_metrics(self):
        """
        Displays performance metrics for a strategy.
        """
        try:
            strategy = self.strategy_manager.list_strategies_for_selection()
            strategy_name = strategy['title']
            metrics = self.performance_manager.calculate_summary(strategy_name)

            print("\n--- Performance Metrics ---")
            for key, value in metrics.items():
                print(f"{key}: {value}")
        except Exception as e:
            self.logger.error(f"Failed to view performance metrics: {e}")
            print(f"Error: {e}")

    def run_backtests(self):
        """
        Runs backtests for a selected strategy with additional options.
        """
        try:
            strategy = self.strategy_manager.list_strategies_for_selection()
            strategy_id = strategy['id']

            print("\n--- Backtesting Options ---")
            print("1. Use historical CSV data")
            print("2. Generate synthetic data")

            choice = input("Choose an option: ").strip()

            if choice == "1":
                historical_data_path = input("Enter the path to historical data (CSV): ").strip()
                from pandas import read_csv
                historical_data = read_csv(historical_data_path)
            elif choice == "2":
                timeframe = input("Enter timeframe for synthetic data (e.g., '1m', '5m', '1h', '1d'): ").strip()
                historical_data = generate_synthetic_data(timeframe)
            else:
                print("Invalid choice.")
                return

            self.backtester.run_backtest(strategy_id, historical_data)
            print(f"Backtest completed for strategy '{strategy['title']}'.")
        except Exception as e:
            self.logger.error(f"Failed to run backtest: {e}")
            print(f"Error: {e}")

    def exit_program(self):
        """
        Exits the program.
        """
        print("Exiting... Goodbye!")
        exit()
