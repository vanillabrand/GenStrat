import os
import logging
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from strategy_manager import StrategyManager
from risk_manager import RiskManager
from budget_manager import BudgetManager
from performance_manager import PerformanceManager
from backtester import Backtester
from dashboard import Dashboard
from synthetic_data_generator import generate_synthetic_data


class UserInterface:
    """
    Handles terminal-based interaction for managing trading strategies, budgets, risk levels, and performance metrics.
    """

    def __init__(self, exchange):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.console = Console()
        self.layout = Layout()
        self.exchange = exchange

        # Initialize managers
        self.strategy_manager = StrategyManager()
        self.risk_manager = RiskManager()
        self.budget_manager = BudgetManager()
        self.performance_manager = PerformanceManager()
        self.backtester = Backtester()
        self.dashboard = Dashboard(
            self.exchange,
            self.strategy_manager,
            self.performance_manager,
        )

        self.configure_layout()

    def configure_layout(self):
        """Configures the rich layout for the application."""
        self.layout.split(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )
        self.layout["header"].update(Panel("[bold cyan]Welcome to GenStrat Trading Application[/bold cyan]"))
        self.layout["footer"].update(
            Panel("Press [bold green]Ctrl+C[/bold green] to exit. Use the menu to navigate options.")
        )

    def clear_screen(self):
        """Clears the terminal screen."""
        os.system("cls" if os.name == "nt" else "clear")

    def main(self):
        """Main loop for the user interface."""
        while True:
            try:
                self.clear_screen()
                self.console.print(self.create_main_menu())
                choice = input("\nSelect an option: ")
                self.handle_menu_choice(choice)
            except KeyboardInterrupt:
                self.exit_program()

    def create_main_menu(self):
        """Creates the main menu as a rich table."""
        table = Table(title="Main Menu", title_style="bold cyan")
        table.add_column("Option", justify="center", style="cyan", no_wrap=True)
        table.add_column("Description", justify="left", style="magenta")

        options = [
            ("1", "Create New Strategy"),
            ("2", "Edit Strategy"),
            ("3", "List Strategies"),
            ("4", "Assign Budget"),
            ("5", "Activate Strategy"),
            ("6", "View Performance Metrics"),
            ("7", "Run Backtests"),
            ("8", "Dashboard"),
            ("9", "Exit"),
        ]

        for option, description in options:
            table.add_row(option, description)

        return Panel(table, title="Main Menu", title_align="left")

    def handle_menu_choice(self, choice):
        """Handles user input for the main menu."""
        menu_options = {
            "1": self.create_new_strategy,
            "2": self.edit_strategy,
            "3": self.list_strategies,
            "4": self.assign_budget,
            "5": self.activate_strategy,
            "6": self.view_performance_metrics,
            "7": self.run_backtests,
            "8": self.view_dashboard,
            "9": self.exit_program,
        }

        action = menu_options.get(choice)
        if action:
            action()
        else:
            self.console.print("[bold red]Invalid choice. Please try again.[/bold red]")
            input("Press Enter to continue...")
                def create_new_strategy(self):
        """Prompts the user to create a new strategy."""
        try:
            title = input("Enter the strategy title: ").strip()
            description = input("Enter the strategy description: ").strip()

            from strategy_interpreter import StrategyInterpreter
            interpreter = StrategyInterpreter()
            strategy_json = interpreter.interpret(description)

            self.strategy_manager.save_strategy(title, description, strategy_json)
            self.console.print(f"[bold green]Strategy '{title}' created successfully.[/bold green]")
        except Exception as e:
            self.logger.error(f"Failed to create a new strategy: {e}")
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    def edit_strategy(self):
        """Allows the user to edit a saved strategy."""
        try:
            strategies = self.strategy_manager.list_strategies()
            self.console.print("\n--- Select a Strategy to Edit ---")
            for i, strategy in enumerate(strategies):
                self.console.print(f"{i + 1}. {strategy['title']} (ID: {strategy['id']})")

            choice = int(input("Select a strategy by number: ")) - 1
            if 0 <= choice < len(strategies):
                strategy_id = strategies[choice]['id']
                strategy = self.strategy_manager.load_strategy(strategy_id)

                updates = {}
                title = input(f"Title [{strategy['title']}]: ").strip()
                if title:
                    updates['title'] = title

                description = input(f"Description [{strategy['description']}]: ").strip()
                if description:
                    updates['description'] = description

                self.strategy_manager.edit_strategy(strategy_id, updates)
                self.console.print(f"[bold green]Strategy '{strategy_id}' updated successfully.[/bold green]")
            else:
                self.console.print("[bold red]Invalid selection.[/bold red]")
        except Exception as e:
            self.logger.error(f"Failed to edit strategy: {e}")
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    def list_strategies(self):
        """Lists all saved strategies."""
        try:
            strategies = self.strategy_manager.list_strategies()
            table = Table(title="Saved Strategies")
            table.add_column("ID", style="cyan")
            table.add_column("Title", style="magenta")
            table.add_column("Active", style="green")

            for strategy in strategies:
                table.add_row(strategy['id'], strategy['title'], str(strategy['active']))

            self.console.print(table)
        except Exception as e:
            self.logger.error(f"Failed to list strategies: {e}")
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    def assign_budget(self):
        """Assigns a budget to a strategy."""
        try:
            strategies = self.strategy_manager.list_strategies()
            self.console.print("\n--- Select a Strategy to Assign Budget ---")
            for i, strategy in enumerate(strategies):
                self.console.print(f"{i + 1}. {strategy['title']} (ID: {strategy['id']})")

            choice = int(input("Select a strategy by number: ")) - 1
            if 0 <= choice < len(strategies):
                strategy_id = strategies[choice]['id']
                amount = float(input("Enter the budget amount (in USDT): "))
                self.budget_manager.set_budget(strategy_id, amount)
                self.console.print(f"[bold green]Budget of {amount} USDT assigned to strategy '{strategy_id}'.[/bold green]")
            else:
                self.console.print("[bold red]Invalid selection.[/bold red]")
        except Exception as e:
            self.logger.error(f"Failed to assign budget: {e}")
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    def activate_strategy(self):
        """Activates a saved strategy for monitoring and execution."""
        try:
            strategies = self.strategy_manager.list_strategies()
            self.console.print("\n--- Select a Strategy to Activate ---")
            for i, strategy in enumerate(strategies):
                self.console.print(f"{i + 1}. {strategy['title']} (ID: {strategy['id']})")

            choice = int(input("Select a strategy by number: ")) - 1
            if 0 <= choice < len(strategies):
                strategy_id = strategies[choice]['id']
                self.strategy_manager.activate_strategy(strategy_id)
                self.console.print(f"[bold green]Strategy '{strategy_id}' activated.[/bold green]")
            else:
                self.console.print("[bold red]Invalid selection.[/bold red]")
        except Exception as e:
            self.logger.error(f"Failed to activate strategy: {e}")
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    def run_backtests(self):
        """Runs backtests for a selected strategy."""
        try:
            strategies = self.strategy_manager.list_strategies()
            self.console.print("\n--- Select a Strategy to Backtest ---")
            for i, strategy in enumerate(strategies):
                self.console.print(f"{i + 1}. {strategy['title']} (ID: {strategy['id']})")
            choice = int(input("Select a strategy by number: ")) - 1

            if 0 <= choice < len(strategies):
                strategy_id = strategies[choice]['id']
                self.console.print("\n1. Load CSV File")
                self.console.print("2. Generate Synthetic Data")
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
                    self.console.print("[bold red]Invalid choice.[/bold red]")
                    return

                strategy = self.strategy_manager.load_strategy(strategy_id)
                self.backtester.run_backtest(strategy, historical_data)
                self.console.print(f"[bold green]Backtest completed for strategy '{strategy_id}'.[/bold green]")
            else:
                self.console.print("[bold red]Invalid selection.[/bold red]")
        except Exception as e:
            self.logger.error(f"Failed to run backtest: {e}")
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    def view_dashboard(self):
        """Displays the live trading dashboard."""
        try:
            self.dashboard.run()
        except Exception as e:
            self.logger.error(f"Failed to display dashboard: {e}")
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    def exit_program(self):
        """Exits the program."""
        self.console.print("[bold cyan]Exiting... Goodbye![/bold cyan]")
        exit()
