import os
import logging
import keyboard
from strategy_manager import StrategyManager
from risk_manager import RiskManager
from budget_manager import BudgetManager
from performance_manager import PerformanceManager
from backtester import Backtester
from synthetic_data_generator import generate_synthetic_data


class UserInterface:
    """
    Handles terminal-based interaction for managing trading strategies, budgets, risk levels, and performance metrics.
    """

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.strategy_manager = StrategyManager()
        self.risk_manager = RiskManager()
        self.budget_manager = BudgetManager()
        self.performance_manager = PerformanceManager()
        self.backtester = Backtester()

    def clear_screen(self):
        """Clear the terminal screen."""
        os.system("cls" if os.name == "nt" else "clear")

    def main(self):
        """
        Main loop for the user interface.
        """
        while True:
            self.clear_screen()
            print("\n--- Main Menu ---")
            print("1. Create New Strategy")
            print("2. Edit Strategy")
            print("3. List Strategies")
            print("4. Assign Budget")
            print("5. Activate Strategy")
            print("6. View Performance Metrics")
            print("7. Run Backtests")
            print("8. Exit")

            choice = input("Enter your choice (Press ESC to exit): ")
            if keyboard.is_pressed("esc"):
                self.exit_program()
            self.handle_menu_choice(choice)

    def handle_menu_choice(self, choice):
        """
        Handles user input for the main menu.
        """
        menu_options = {
            "1": self.create_new_strategy,
            "2": self.edit_strategy,
            "3": self.list_strategies,
            "4": self.assign_budget,
            "5": self.activate_strategy,
            "6": self.view_performance_metrics,
            "7": self.run_backtests,
            "8": self.exit_program,
        }

        action = menu_options.get(choice)
        if action:
            action()
        else:
            print("Invalid choice. Please try again.")
            input("Press Enter to continue...")

    def create_new_strategy(self):
        """
        Prompts the user to create a new strategy, interprets it, and saves it.
        """
        self.clear_screen()
        try:
            title = input("Enter the strategy title: ")
            description = input("Enter the strategy description: ")

            from strategy_interpreter import StrategyInterpreter
            interpreter = StrategyInterpreter()
            strategy_json = interpreter.interpret(description)

            self.strategy_manager.save_strategy(title, description, strategy_json)
            print(f"Strategy '{title}' created successfully.")
        except Exception as e:
            self.logger.error(f"Failed to create a new strategy: {e}")
            print(f"Error: {e}")
        input("Press Enter to return to the main menu...")

    def edit_strategy(self):
        """
        Allows the user to edit a saved strategy.
        """
        self.clear_screen()
        try:
            strategies = self.strategy_manager.list_strategies()
            print("\n--- Select a Strategy to Edit ---")
            for i, strategy in enumerate(strategies):
                print(f"{i + 1}. {strategy['title']} (ID: {strategy['id']})")
            choice = int(input("Select a strategy by number: ")) - 1

            if 0 <= choice < len(strategies):
                strategy_id = strategies[choice]['id']
                strategy = self.strategy_manager.load_strategy(strategy_id)

                print("\n--- Editing Strategy ---")
                print("Leave fields blank to keep the current value.")

                updates = {}
                title = input(f"Title [{strategy['title']}]: ")
                if title:
                    updates['title'] = title

                description = input(f"Description [{strategy['description']}]: ")
                if description:
                    updates['description'] = description

                # Editing risk parameters
                print("\n--- Risk Parameters ---")
                risk_updates = {}
                for param in ["stop_loss", "take_profit", "trailing_stop_loss"]:
                    current = strategy['data']['risk_management'].get(param, None)
                    new_value = input(f"{param.replace('_', ' ').capitalize()} [{current}]: ")
                    if new_value:
                        risk_updates[param] = float(new_value)
                if risk_updates:
                    updates['data'] = {"risk_management": risk_updates}

                self.strategy_manager.edit_strategy(strategy_id, updates)
                print(f"Strategy '{strategy_id}' updated successfully.")
            else:
                print("Invalid selection.")
        except Exception as e:
            self.logger.error(f"Failed to edit strategy: {e}")
            print(f"Error: {e}")
        input("Press Enter to return to the main menu...")

    def list_strategies(self):
        """
        Lists all saved strategies.
        """
        self.clear_screen()
        try:
            strategies = self.strategy_manager.list_strategies()
            print("\n--- Strategies ---")
            for strategy in strategies:
                print(f"ID: {strategy['id']}, Title: {strategy['title']}, Active: {strategy['active']}")
        except Exception as e:
            self.logger.error(f"Failed to list strategies: {e}")
            print(f"Error: {e}")
        input("Press Enter to return to the main menu...")

    def assign_budget(self):
        """
        Assigns a budget to a strategy.
        """
        self.clear_screen()
        try:
            strategies = self.strategy_manager.list_strategies()
            print("\n--- Select a Strategy to Assign Budget ---")
            for i, strategy in enumerate(strategies):
                print(f"{i + 1}. {strategy['title']} (ID: {strategy['id']})")
            choice = int(input("Select a strategy by number: ")) - 1

            if 0 <= choice < len(strategies):
                strategy_id = strategies[choice]['id']
                amount = float(input("Enter the budget amount (in USDT): "))
                self.budget_manager.set_budget(strategy_id, amount)
                print(f"Budget of {amount} USDT assigned to strategy '{strategy_id}'.")
            else:
                print("Invalid selection.")
        except Exception as e:
            self.logger.error(f"Failed to assign budget: {e}")
            print(f"Error: {e}")
        input("Press Enter to return to the main menu...")

    def activate_strategy(self):
        """
        Activates a saved strategy for monitoring and execution.
        """
        self.clear_screen()
        try:
            strategies = self.strategy_manager.list_strategies()
            print("\n--- Select a Strategy to Activate ---")
            for i, strategy in enumerate(strategies):
                print(f"{i + 1}. {strategy['title']} (ID: {strategy['id']})")
            choice = int(input("Select a strategy by number: ")) - 1

            if 0 <= choice < len(strategies):
                strategy_id = strategies[choice]['id']
                self.strategy_manager.activate_strategy(strategy_id)
                print(f"Strategy '{strategy_id}' activated.")
            else:
                print("Invalid selection.")
        except Exception as e:
            self.logger.error(f"Failed to activate strategy: {e}")
            print(f"Error: {e}")
        input("Press Enter to return to the main menu...")

    def view_performance_metrics(self):
        """
        Displays performance metrics for a strategy.
        """
        self.clear_screen()
        try:
            strategies = self.strategy_manager.list_strategies()
            print("\n--- Select a Strategy to View Performance ---")
            for i, strategy in enumerate(strategies):
                print(f"{i + 1}. {strategy['title']} (ID: {strategy['id']})")
            choice = int(input("Select a strategy by number: ")) - 1

            if 0 <= choice < len(strategies):
                strategy_id = strategies[choice]['id']
                metrics = self.performance_manager.calculate_summary(strategy_id)
                print("\n--- Performance Metrics ---")
                for key, value in metrics.items():
                    print(f"{key}: {value}")
            else:
                print("Invalid selection.")
        except Exception as e:
            self.logger.error(f"Failed to view performance metrics: {e}")
            print(f"Error: {e}")
        input("Press Enter to return to the main menu...")

    def run_backtests(self):
        """
        Runs backtests for a selected strategy.
        """
        self.clear_screen()
        try:
            strategies = self.strategy_manager.list_strategies()
            print("\n--- Select a Strategy to Backtest ---")
            for i, strategy in enumerate(strategies):
                print(f"{i + 1}. {strategy['title']} (ID: {strategy['id']})")
            choice = int(input("Select a strategy by number: ")) - 1

            if 0 <= choice < len(strategies):
                strategy_id = strategies[choice]['id']
                print("\n1. Load CSV File")
                print("2. Generate Synthetic Data")
                source_choice = input("Choose data source: ")

                if source_choice == "1":
                    historical_data_path = input("Enter the path to historical data (CSV): ")
                    from pandas import read_csv
                    historical_data = read_csv(historical_data_path)
                elif source_choice == "2":
                    timeframe = input("Enter timeframe (e.g., 1m, 5m, 1h): ")
                    duration = int(input("Enter duration in days: "))
                    historical_data = generate_synthetic_data(timeframe, duration)
                else:
                    print("Invalid choice.")
                    return

                strategy = self.strategy_manager.load_strategy(strategy_id)
                self.backtester.run_backtest(strategy, historical_data)
                print(f"Backtest completed for strategy '{strategy_id}'.")
            else:
                print("Invalid selection.")
        except Exception as e:
            self.logger.error(f"Failed to run backtest: {e}")
            print(f"Error: {e}")
        input("Press Enter to return to the main menu...")

    def exit_program(self):
        """
        Exits the program.
        """
        print("Exiting... Goodbye!")
        exit()
