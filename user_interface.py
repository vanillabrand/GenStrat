import os
import logging
import asyncio
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from strategy_manager import StrategyManager
from risk_manager import RiskManager
from budget_manager import BudgetManager
from trade_manager import TradeManager
from performance_manager import PerformanceManager
from backtester import Backtester
from dashboard import Dashboard
from strategy_interpreter import StrategyInterpreter
from market_monitor import MarketMonitor
from trade_executor import TradeExecutor
from trade_suggestion_manager import TradeSuggestionManager  
from typing import Any, Optional


class UserInterface:
    """Handles terminal-based interaction for managing trading strategies."""

    def __init__(self, exchange: Any, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.console = Console()
        self.layout = Layout()
        self.exchange = exchange

        # Initialize managers in dependency order
        self.risk_manager = RiskManager()
        self.budget_manager = BudgetManager()
        self.trade_manager = TradeManager()
        
        self.performance_manager = PerformanceManager(self.trade_manager)
        self.strategy_manager = StrategyManager(self.trade_manager)
        
        # Initialize trading components
        self.trade_suggestion_manager = TradeSuggestionManager(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            trade_manager=self.trade_manager
        )
        
        self.trade_executor = TradeExecutor(
            exchange=self.exchange,
            trade_manager=self.trade_manager,
            budget_manager=self.budget_manager
        )
        
        self.market_monitor = MarketMonitor(
            exchange=self.exchange,
            strategy_manager=self.strategy_manager,
            trade_manager=self.trade_manager, 
            trade_executor=self.trade_executor,
            budget_manager=self.budget_manager,
            trade_suggestion_manager=self.trade_suggestion_manager
        )

        # Initialize dashboard last since it depends on other components
        self.dashboard = Dashboard(
            strategy_manager=self.strategy_manager,
            trade_manager=self.trade_manager,
            performance_manager=self.performance_manager
        )
        # Link dependencies
      
        self.market_monitor.dashboard = self.dashboard
        self.strategy_manager.set_monitoring(self.market_monitor)
        self.backtester = Backtester(self.strategy_manager, self.budget_manager, self.risk_manager, self.trade_suggestion_manager)
        self.configure_layout()

    async def start(self):
            """Start the user interface and dashboard."""
            try:
                await self.dashboard.start()
            except Exception as e:
                self.logger.error(f"Failed to start UI: {str(e)}")
                raise

    async def stop(self):
        """Clean shutdown of all components."""
        try:
            await self.trade_executor.stop()
            await self.market_monitor.stop()
            # Add other cleanup tasks as needed
        except Exception as e:
            self.logger.error(f"Error during shutdown: {str(e)}")
            raise
                        
    def configure_layout(self):
        """Configures the rich layout for the application."""
        self.layout.split(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )
        self.layout["header"].update(Panel("[bold cyan]Welcome to GenStrat Trading Application[/bold cyan]"))
        self.layout["footer"].update(
            Panel(
                "Press [bold green]Ctrl+C[/bold green] to exit. Use the menu to navigate options."
            )
        )

    def clear_screen(self):
        """Clears the terminal screen."""
        os.system("cls" if os.name == "nt" else "clear")

    async def main(self):
            """Main loop for the user interface."""
            while True:
                try:
                    self.clear_screen()
                    self.console.print(self.create_main_menu())
                    choice = input("\nSelect an option: ")
                    await self.handle_menu_choice(choice)
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
            ("6", "Deactivate Strategy"),
            ("7", "Remove Strategy"),
            ("8", "View Performance Metrics"),
            ("9", "Run Backtests"),
            ("10", "Run Scenario Tests"),  # New option for Scenario Testing
            ("11", "Dashboard"),
            ("12", "Exit"),
        ]

        for option, description in options:
            table.add_row(option, description)

        return Panel(table, title="Main Menu", title_align="left")


    async def handle_menu_choice(self, choice):
        """Handles user input for the main menu."""
        menu_options = {
            "1": self.create_new_strategy,
            "2": self.edit_strategy,
            "3": self.list_strategies,
            "4": self.assign_budget,
            "5": self.activate_strategy,
            "6": self.deactivate_strategy,  # Link to Deactivate Strategy
            "7": self.remove_strategy,  # Link to Remove Strategy
            "8": self.view_performance_metrics,
            "9": self.run_backtest,
            "10": self.run_scenario_tests,  # Link to Scenario Testing
            "11": self.view_dashboard,
            "12": self.exit_program,
        }

        action = menu_options.get(choice)
        if action:
            if asyncio.iscoroutinefunction(action):
                await action()
            else:
                action()
            input("Press Enter to return to the main menu...")  # Pause for user to view results
        else:
            self.console.print("[bold red]Invalid choice. Please try again.[/bold red]")
            input("Press Enter to continue...")


    def get_strategy_selection(self, prompt: str):
        """
        Lists strategies and prompts the user to select one by index.
        :param prompt: Instructional text for the user.
        :return: The selected strategy dictionary or None if invalid.
        """
        strategies = self.list_strategies()
        if not strategies:
            self.console.print("[bold red]No strategies found. Returning to main menu.[/bold red]")
            return None

        try:
            choice = int(input(f"{prompt} (Enter a number): ")) - 1
            if 0 <= choice < len(strategies):
                return strategies[choice]
            else:
                self.console.print("[bold red]Invalid selection. Returning to main menu.[/bold red]")
                return None
        except ValueError:
            self.console.print("[bold red]Invalid input. Please enter a number.[/bold red]")
            return None

    async def create_new_strategy(self):
        """Prompts the user to create a new strategy."""
        try:
            title = input("Enter the strategy title: ").strip()
            description = input("Enter the strategy description: ").strip()

            interpreter = StrategyInterpreter(os.getenv("OPENAI_API_KEY"))
            strategy_json = interpreter.interpret(description)

            self.strategy_manager.save_strategy(title, description, strategy_json)
            self.console.print(f"[bold green]Strategy '{title}' created successfully.[/bold green]")
        except Exception as e:
            self.logger.error(f"Failed to create a new strategy: {e}")
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    def list_strategies(self):
        """Lists all saved strategies."""
        try:
            strategies = self.strategy_manager.list_strategies()
            table = Table(title="Saved Strategies", title_style="bold cyan")
            table.add_column("Index", style="magenta", justify="center")
            table.add_column("Title", style="cyan", justify="left")
            table.add_column("Active", style="green", justify="center")

            for i, strategy in enumerate(strategies, start=1):
                table.add_row(str(i), strategy['title'], "Yes" if strategy['active'] else "No")

            self.console.print(table)
            return strategies
        except Exception as e:
            self.logger.error(f"Failed to list strategies: {e}")
            self.console.print(f"[bold red]Error: {e}[/bold red]")
            return []

    def edit_strategy(self):
        """
        Allows the user to edit a saved strategy.
        """
        try:
            strategies = self.list_strategies()
            if not strategies:
                self.console.print("[bold red]No strategies available to edit. Returning to the main menu.[/bold red]")
                return

            # Prompt the user to select a strategy
            self.console.print("\n--- Select a Strategy to Edit ---")
            for i, strategy in enumerate(strategies, start=1):
                self.console.print(f"{i}. {strategy['title']} (ID: {strategy['id']})")

            choice = int(input("Select a strategy by number: ")) - 1
            if 0 <= choice < len(strategies):
                strategy_id = strategies[choice]['id']
                strategy = self.strategy_manager.load_strategy(strategy_id)

                updates = {}
                title = input(f"New Title [{strategy['title']}]: ").strip()
                if title:
                    updates['title'] = title

                description = input(f"New Description [{strategy['description']}]: ").strip()
                if description:
                    updates['description'] = description

                self.strategy_manager.edit_strategy(strategy_id, updates)
                self.console.print(f"[bold green]Strategy '{strategy['title']}' updated successfully.[/bold green]")
            else:
                self.console.print("[bold red]Invalid selection. Returning to the main menu.[/bold red]")
        except ValueError:
            self.console.print("[bold red]Invalid input. Please enter a valid number.[/bold red]")
        except Exception as e:
            self.logger.error(f"Failed to edit strategy: {e}")
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    def run_scenario_tests(self):
        """Prompts the user to run scenario tests."""
        strategy = self.get_strategy_selection("Select a strategy to run scenario tests")
        if not strategy:
            return

        strategy_id = strategy["id"]
        print("\n--- Select a Scenario ---")
        print("1. Bull Market")
        print("2. Bear Market")
        print("3. Sideways Market")
        print("4. High Volatility")
        print("5. Low Volatility")
        scenario_choice = input("Choose a scenario: ")

        scenarios = {
            "1": "bull",
            "2": "bear",
            "3": "sideways",
            "4": "high_volatility",
            "5": "low_volatility"
        }
        scenario = scenarios.get(scenario_choice)

        if not scenario:
            print("[bold red]Invalid choice. Returning to main menu.[/bold red]")
            return

        timeframe = input("Enter timeframe (e.g., 1m, 5m, 1h): ")
        duration_days = int(input("Enter duration in days: "))

        try:
            self.backtester.run_scenario_test(strategy_id, scenario, timeframe, duration_days)
        except Exception as e:
            self.logger.error(f"Failed to run scenario tests: {e}")
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    def assign_budget(self):
        """Assigns a budget to a strategy."""
        try:
            strategy = self.get_strategy_selection("Select a strategy to assign a budget")
            if not strategy:
                return

            strategy_id = strategy['id']
            amount = float(input("Enter the budget amount (in USDT): "))
            self.budget_manager.set_budget(strategy_id, amount)
            self.console.print(f"[bold green]Budget of {amount} USDT assigned to strategy '{strategy['title']}'.[/bold green]")
        except Exception as e:
            self.logger.error(f"Failed to assign budget: {e}")
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    async def activate_strategy(self):
        """
        Activates a saved strategy for live trading with budget allocation.
        """
        try:
            strategy = self.get_strategy_selection("Select a strategy to activate")
            if not strategy:
                return

            strategy_id = strategy["id"]

            # Check if a budget is set
            budget = self.budget_manager.get_budget(strategy_id)
            if budget <= 0:
                self.console.print(f"[bold red]No budget assigned to strategy '{strategy['title']}'. Assign a budget before activating.[/bold red]")
                return

            # Activate the strategy
            self.strategy_manager.activate_strategy(strategy_id)

            # Generate initial trades based on entry conditions
            strategy_data = self.strategy_manager.load_strategy(strategy_id)
            assets = strategy_data.get("assets", [])
            market_data = {
                asset: await self.trade_suggestion_manager.fetch_market_data(asset, strategy_data["market_type"], self.exchange)
                for asset in assets
            }

            self.console.print(f"Market Data {market_data}")

            # Generate trades with budget allocation
            suggested_trades = self.trade_suggestion_manager.generate_trades(strategy_data, market_data, budget)

    
            self.console.print(f"[bold green]Strategy '{strategy['title']}' activated and trades generated.[/bold green]")

        except Exception as e:
            self.logger.error(f"Failed to activate strategy: {e}")
            self.console.print(f"[bold red]Error: {e}[/bold red]")


    async def deactivate_strategy(self):
            """Deactivates a saved strategy."""
            try:
                strategy = self.get_strategy_selection("Select a strategy to deactivate")
                if not strategy:
                    return

                strategy_id = strategy['id']
                await self.strategy_manager.deactivate_strategy(strategy_id)
                self.console.print(f"[bold green]Strategy '{strategy['title']}' deactivated successfully.[/bold green]")
            except Exception as e:
                self.logger.error(f"Failed to deactivate strategy: {e}")
                self.console.print(f"[bold red]Error: {e}[/bold red]")


    def view_performance_metrics(self):
        """Displays performance metrics for a strategy."""
        try:
            strategy = self.get_strategy_selection("Select a strategy to view performance")
            if not strategy:
                return

            strategy_id = strategy['id']
            metrics = self.performance_manager.calculate_summary(strategy_id)
            table = Table(title=f"Performance Metrics for '{strategy['title']}'")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="magenta")

            for key, value in metrics.items():
                table.add_row(key, str(value))

            self.console.print(table)
        except Exception as e:
            self.logger.error(f"Failed to view performance metrics: {e}")
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    async def run_backtest(self):
        """
        Prompts the user to run a backtest, including budget allocation.
        """
        try:
            # Select strategy
            strategy = self.get_strategy_selection("Select a strategy to run backtests")
            if not strategy:
                return

            # Prompt for historical data source
            source = input("Enter the source - y for synthetic: ").strip()
            if source.lower() == "y":
                # Generate synthetic data
                scenario = input("Enter market scenario (bull, bear, sideways): ").strip().lower()
                timeframe = input("Enter timeframe (e.g., 1m, 5m, 1h): ").strip()
                duration_days = int(input("Enter duration in days: ").strip())
                historical_data = self.backtester.generate_synthetic_data(scenario, timeframe, duration_days)
            else:
                # Load historical data from CSV
                historical_data = pd.read_csv(source)

            # Prompt for budget
            budget = float(input("Enter total budget for the backtest (in USDT): ").strip())

            # Run backtest
            strategy_id = strategy["id"]
            results = self.backtester.run_backtest(strategy_id, historical_data, budget)
            self.console.print(f"[bold green]Backtest completed for strategy '{strategy['title']}'.[/bold green]")
            self.console.print(f"Final Portfolio Value: {results['final_portfolio_value']:.2f} USDT")

        except Exception as e:
            self.logger.error(f"Failed to run backtests: {e}")
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    def remove_strategy(self):
        """Allows the user to remove a saved strategy."""
        try:
            strategy = self.get_strategy_selection("Select a strategy to remove")
            if not strategy:
                return

            strategy_id = strategy['id']
            self.strategy_manager.remove_strategy(strategy_id)
            self.console.print(f"[bold green]Strategy '{strategy['title']}' removed successfully.[/bold green]")
        except Exception as e:
            self.logger.error(f"Failed to remove strategy: {e}")
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    async def view_dashboard(self):
        """Displays the live trading dashboard."""
        try:
            self.console.print("[bold cyan]Launching the live trading dashboard...[/bold cyan]")
            await self.dashboard.run()  # Ensure the coroutine is awaited
        except Exception as e:
            self.logger.error(f"Failed to display dashboard: {e}")
            self.console.print(f"[bold red]Error: {e}[/bold red]")
        def exit_program(self):
            """Exits the program."""
            self.console.print("[bold cyan]Exiting the program... Goodbye![/bold cyan]")
            exit(0)

            
    async def exit_program(self):
            """Exits the program."""
            self.console.print("[bold cyan]Exiting the program... Goodbye![/bold cyan]")
            await asyncio.sleep(1)
            exit(0)
