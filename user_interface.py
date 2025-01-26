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
        
        # Initialize TradeExecutor first
        self.trade_executor = TradeExecutor(
            exchange=self.exchange,
            trade_manager=self.trade_manager,
            budget_manager=self.budget_manager
        )

        # Initialize MarketMonitor first
        self.market_monitor = MarketMonitor(
            exchange=self.exchange,
            trade_monitor=self.trade_manager,
            trade_suggestion_manager=None  # Placeholder, will be set later
        )
        
        # Initialize TradeSuggestionManager with MarketMonitor
        self.trade_suggestion_manager = TradeSuggestionManager(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            strategy_manager=self.strategy_manager,
            trade_manager=self.trade_manager,
            exchange=self.exchange,
            market_monitor=self.market_monitor
        )
        
        # Set the TradeSuggestionManager in MarketMonitor
        self.market_monitor.trade_suggestion_manager = self.trade_suggestion_manager
        
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

            asyncio.create_task(self.market_monitor.start_websocket_monitoring())
     
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


    async def get_strategy_selection(self, prompt: str):
        """
        Lists strategies and prompts the user to select one by index.
        """
        strategies = await self.strategy_manager.list_strategies()
        if not strategies:
            self.console.print("[bold red]No strategies found. Returning to main menu.[/bold red]")
            return None

        try:
            # Display strategies
            self.console.print("\n--- Available Strategies ---")
            for i, strategy in enumerate(strategies, start=1):
                self.console.print(f"{i}. {strategy['title']} (ID: {strategy['id']})")

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

    async def list_strategies(self):
        """
        Lists all saved strategies using the StrategyManager and displays them in a formatted table.
        """
        try:
            # Fetch strategies from StrategyManager
            strategies = await self.strategy_manager.list_strategies()

            if not strategies:
                self.console.print("[bold red]No strategies found. Returning to main menu.[/bold red]")
                return

            # Prepare table for display
            table = Table(title="Saved Strategies", title_style="bold cyan")
            table.add_column("Index", style="magenta", justify="center")
            table.add_column("Title", style="cyan", justify="left")
            table.add_column("Active", style="green", justify="center")
            table.add_column("Market Type", style="yellow", justify="center")
            table.add_column("Assets", style="blue", justify="left")
            table.add_column("Number of Trades", style="red", justify="center")

            for idx, strategy in enumerate(strategies, start=1):
                assets = ", ".join(strategy.get("assets", []))
                active_status = "Yes" if strategy.get("active", False) else "No"
                num_trades = len(strategy.get("trades", []))
                market_type = strategy.get("market_type", "Unknown")
                table.add_row(
                    str(idx),
                    strategy.get("title", "N/A"),
                    active_status,
                    market_type,
                    assets,
                    str(num_trades),
                )

            self.console.print(table)

        except Exception as e:
            self.logger.error(f"Failed to list strategies: {e}", exc_info=True)
            self.console.print(f"[bold red]Error listing strategies: {e}[/bold red]")


    async def edit_strategy(self):
        """Allows the user to edit a saved strategy."""
        try:
            strategy = await self.get_strategy_selection("Select a strategy to edit")
            if not strategy:
                return

            # Rest of the edit strategy logic
            strategy_id = strategy['id']
            updates = {}
            title = input(f"New Title [{strategy['title']}]: ").strip()
            if title:
                updates['title'] = title

            description = input(f"New Description [{strategy['description']}]: ").strip()
            if description:
                updates['description'] = description

            await self.strategy_manager.edit_strategy(strategy_id, updates)
            self.console.print(f"[bold green]Strategy updated successfully.[/bold green]")
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

    async def assign_budget(self):
        """
        Assigns a budget to a strategy.
        """
        try:
            # Await the strategy selection
            strategy = await self.get_strategy_selection("Select a strategy to assign a budget")
            if not strategy:
                return

            strategy_id = strategy["id"]

            # Prompt the user for budget input
            amount = float(input("Enter the budget amount (in USDT): "))

            # Assign the budget using the BudgetManager
            await self.budget_manager.set_budget(strategy_id, amount)

            self.console.print(f"[bold green]Budget of {amount} USDT assigned to strategy '{strategy['title']}'.[/bold green]")

        except Exception as e:
            self.logger.error(f"Failed to assign budget: {e}", exc_info=True)
            self.console.print(f"[bold red]Error: {e}[/bold red]")


    async def activate_strategy(self):
        """
        Activates a saved strategy for live trading with budget allocation.
        """
        try:
            strategy = await self.get_strategy_selection("Select a strategy to activate")
            if not strategy:
                return

            strategy_id = strategy["id"]

            # Check if a budget is set
            budget = await self.budget_manager.get_budget(strategy_id)
            if budget <= 0:
                self.console.print(f"[bold red]No budget assigned to strategy '{strategy['title']}'. Assign a budget before activating.[/bold red]")
                return

            # Load strategy data for the selected strategy
            await self.strategy_manager.activate_strategy(strategy_id)

            # Generate trades with budget allocation
            suggested_trades = await self.trade_suggestion_manager.process_strategy_trades(strategy_id, budget)
            self.logger.info(f"Generated {len(suggested_trades)} trades for strategy '{strategy['title']}'.")

            self.console.print(f"[bold green]Strategy '{strategy['title']}' activated and {len(suggested_trades)} trades generated.[/bold green]")

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
        """Execute a backtest for a selected strategy."""
        try:
            # Step 1: Strategy Selection
            strategy = self.get_strategy_selection("Select a strategy to backtest")
            if not strategy:
                return

            # Load strategy data
            strategy_id = strategy["id"]
            strategy_data = self.strategy_manager.load_strategy(strategy_id)

            # Extract asset pairs from strategy JSON
            trading_pairs = strategy_data.get("data", {}).get("assets", [])
            if not trading_pairs:
                self.console.print(f"[bold red]No trading pairs found in the selected strategy.[/bold red]")
                return

            # Step 2: Data Source Selection
            self.console.print("\n[bold cyan]Select Data Source:[/bold cyan]")
            self.console.print("1. Synthetic Data")
            self.console.print("2. CSV File")
            self.console.print("3. Historical Data from Exchange (for strategy assets)")

            source_choice = input("Choose the data source (1/2/3): ").strip()

            if source_choice == "1":
                # Synthetic Data
                scenario = input("Enter market scenario (bull, bear, sideways): ").strip().lower()
                timeframe = input("Enter timeframe (e.g., 1m, 5m, 1h): ").strip()
                duration_days = int(input("Enter duration in days: ").strip())
                historical_data = await self.backtester.generate_synthetic_data(
                    scenario=scenario,
                    timeframe=timeframe,
                    duration_days=duration_days
                )
            elif source_choice == "2":
                # CSV Data
                csv_path = input("Enter the path to the CSV file: ").strip()
                try:
                    historical_data = pd.read_csv(csv_path)
                    self.console.print(f"[bold green]Loaded data from {csv_path}.[/bold green]")
                except Exception as e:
                    self.console.print(f"[bold red]Error loading CSV file: {e}[/bold red]")
                    return
            elif source_choice == "3":
                # Exchange Data for Strategy Assets
                self.console.print(f"[bold cyan]Fetching historical data for assets: {trading_pairs}[/bold cyan]")
                timeframe = input("Enter the timeframe (e.g., 1m, 5m, 1h): ").strip()
                start_date = input("Enter the start date (YYYY-MM-DD): ").strip()
                end_date = input("Enter the end date (YYYY-MM-DD): ").strip()

                try:
                    # Convert user input to timestamps
                    start_timestamp = int(pd.Timestamp(start_date).timestamp() * 1000)  # ms
                    end_timestamp = int(pd.Timestamp(end_date).timestamp() * 1000)  # ms

                    historical_data_list = []
                    for asset in trading_pairs:
                        self.console.print(f"[bold cyan]Fetching data for {asset}...[/bold cyan]")
                        ohlcv = self.exchange.fetch_ohlcv(asset, timeframe, since=start_timestamp)
                        # Filter the data to ensure it matches the provided time range
                        filtered_data = [
                            row for row in ohlcv if start_timestamp <= row[0] <= end_timestamp
                        ]
                        data = pd.DataFrame(
                            filtered_data,
                            columns=["timestamp", "open", "high", "low", "close", "volume"]
                        )
                        data["asset"] = asset
                        data["timestamp"] = pd.to_datetime(data["timestamp"], unit="ms")
                        historical_data_list.append(data)

                    # Combine data from all assets into one DataFrame
                    historical_data = pd.concat(historical_data_list, ignore_index=True)
                    self.console.print(f"[bold green]Fetched historical data from the exchange for all strategy assets.[/bold green]")
                except Exception as e:
                    self.console.print(f"[bold red]Error fetching data from the exchange: {e}[/bold red]")
                    return
            else:
                self.console.print("[bold red]Invalid selection. Returning to the main menu.[/bold red]")
                return

            # Step 3: Validate Strategy and Execute Backtest
            # Pre-validate and fetch prices
            # validated_data = await self.backtester.pre_validate_and_fetch_prices(strategy_id)

            # Run Backtest
            results = await self.backtester.run_backtest(
                strategy_id=strategy_id,
                historical_data=historical_data
            )

            # Step 4: Display Results
            self.console.print(f"[bold green]Backtest completed for '{strategy['title']}'[/bold green]")
            self.console.print(f"Initial Value: {results['initial_value']:.2f} USDT")
            self.console.print(f"Final Value: {results['final_value']:.2f} USDT")
            self.console.print(f"Total Return: {results['return']:.2f}%")
            self.console.print(f"Sharpe Ratio: {results['sharpe_ratio']:.2f}")
            self.console.print(f"Max Drawdown: {results['max_drawdown']:.2f}%")
            self.console.print(f"Win Rate: {results['win_rate']:.2f}%")

        except Exception as e:
            self.logger.error(f"Failed to run backtest: {e}")
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    async def remove_strategy(self):
        """Allows the user to remove a saved strategy."""
        try:
            strategy = await self.get_strategy_selection("Select a strategy to remove")
            if not strategy:
                return

            strategy_id = strategy['id']
            await self.strategy_manager.remove_strategy(strategy_id)
            self.console.print(f"[bold green]Strategy removed successfully.[/bold green]")
        except Exception as e:
            self.logger.error(f"Failed to remove strategy: {e}")
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    async def view_dashboard(self):
        """Displays the live trading dashboard."""
        try:
            self.console.print("[bold cyan]Launching the live trading dashboard...[/bold cyan]")
            await self.dashboard.start()  # Ensure the coroutine is awaited
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

    async def validate_strategy(self, strategy_id: str):
        """Validate strategy with market data."""
        try:
            return await self.backtester.pre_validate_and_fetch_prices(strategy_id)
        except Exception as e:
            self.logger.error(f"Strategy validation failed: {e}")
            raise


