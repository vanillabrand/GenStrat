import os
import logging
import asyncio
import pandas as pd
from aioconsole import ainput  # For asynchronous, non-blocking input
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.align import Align
from typing import Any, Optional, Dict

# Import your custom managers and classes
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

class UserInterface:
    """Handles terminal-based interaction for managing trading strategies with a modern, visually impressive interface."""

    # Updated ASCII art banner for "STRATGEN"
    ASCII_BANNER = r"""
  ____  ____  ____  _____  _______ _____  
 / ___||  _ \|  _ \| ____|| ____|_   _| 
 \___ \| |_) | | | |  _|  |  _|   | |   
  ___) |  __/| |_| | |___ | |___  | |   
 |____/|_|   |____/|_____||_____| |_|   
                                         
  ____  ____  _____  _____  _   _ 
 / ___||  _ \| ____|| ____|| \ | |
 \___ \| |_) |  _|  |  _|  |  \| |
  ___) |  __/| |___ | |___ | |\  |
 |____/|_|   |_____||_____||_| \_|
"""

    def __init__(self, exchange: Any, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.console = Console()
        self.layout = Layout()
        self.exchange = exchange

        # Initialize managers (in dependency order)
        self.risk_manager = RiskManager()
        self.budget_manager = BudgetManager()
        self.trade_manager = TradeManager()
        self.performance_manager = PerformanceManager(self.trade_manager)
       
        # Initialize TradeExecutor
        self.trade_executor = TradeExecutor(
            exchange=self.exchange,
            trade_manager=self.trade_manager,
            budget_manager=self.budget_manager
        )

        # Initialize MarketMonitor and TradeSuggestionManager
        self.market_monitor = MarketMonitor(
            exchange=self.exchange,
            trade_monitor=self.trade_manager,
            trade_suggestion_manager=None  # Placeholder; will be set below
        )

        self.strategy_manager = StrategyManager(self.trade_manager, self.performance_manager, self.market_monitor)

        self.trade_suggestion_manager = TradeSuggestionManager(
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            strategy_manager=self.strategy_manager,
            trade_manager=self.trade_manager,
            exchange=self.exchange,
            market_monitor=self.market_monitor
        )
        self.market_monitor.trade_suggestion_manager = self.trade_suggestion_manager

        self.strategy_manager.setTradeSuggestionManager(self.trade_suggestion_manager)

        # Initialize Dashboard and Backtester
        self.dashboard = Dashboard(
            strategy_manager=self.strategy_manager,
            trade_manager=self.trade_manager,
            performance_manager=self.performance_manager,
            exchange=self.exchange
        )
        self.market_monitor.dashboard = self.dashboard
        self.strategy_manager.set_monitoring(self.market_monitor)
        self.backtester = Backtester(
            self.strategy_manager,
            self.budget_manager,
            self.risk_manager,
            self.trade_suggestion_manager,
            exchange=self.exchange
        )

        self.configure_layout()

    def configure_layout(self):
        """Configures the overall Rich layout for the application."""
        self.layout.split(
            Layout(name="header", size=7),
            Layout(name="body"),
            Layout(name="footer", size=3)
        )
        header_panel = Panel(
            Align.center(self.ASCII_BANNER, vertical="middle"),
            style="bold magenta", border_style="bright_blue"
        )
        self.layout["header"].update(header_panel)
        self.layout["footer"].update(
            Panel("Press [bold green]Ctrl+C[/bold green] to exit. Navigate with menu options.", style="bold cyan")
        )

    def clear_screen(self):
        """Clears the terminal screen."""
        os.system("cls" if os.name == "nt" else "clear")

    async def start(self):
        """Starts background tasks (e.g. MarketMonitor) and enters the main menu loop."""
        asyncio.create_task(self.market_monitor.start_websocket_monitoring())
        await self.main()

    async def main(self):
        """
        Main loop for the user interface.
        Uses aioconsole.ainput() for asynchronous input so that other tasks remain responsive.
        """
        while True:
            try:
                self.clear_screen()
                self.console.print(self.create_main_menu())
                choice = (await ainput("\nSelect an option: ")).strip()
                if not choice:
                    continue
                await self.handle_menu_choice(choice)
            except KeyboardInterrupt:
                await self.exit_program()
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)
                await asyncio.sleep(1)

    def create_main_menu(self) -> Panel:
        """Creates a visually impressive main menu panel with an ASCII banner and options table."""
        menu_table = Table(show_header=True, header_style="bold blue")
        menu_table.add_column("Option", justify="center", style="cyan", no_wrap=True)
        menu_table.add_column("Description", style="magenta")
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
            ("10", "Run Scenario Tests"),
            ("11", "Launch Dashboard"),
            ("12", "Exit")
        ]
        for opt, desc in options:
            menu_table.add_row(opt, desc)
        return Panel.fit(menu_table, title="MAIN MENU", subtitle="Select an option", title_align="left", border_style="green")

    async def handle_menu_choice(self, choice: str):
        """Dispatches the menu selection to the corresponding action."""
        menu_actions: Dict[str, Any] = {
            "1": self.create_new_strategy,
            "2": self.edit_strategy,
            "3": self.list_strategies,
            "4": self.assign_budget,
            "5": self.activate_strategy,
            "6": self.deactivate_strategy,
            "7": self.remove_strategy,
            "8": self.view_performance_metrics,
            "9": self.run_backtest,
            "10": self.run_scenario_tests,
            "11": self.view_dashboard,
            "12": self.exit_program
        }
        action = menu_actions.get(choice)
        if action:
            if asyncio.iscoroutinefunction(action):
                await action()
            else:
                action()
            await ainput("Press Enter to return to the main menu...")
        else:
            self.console.print("[bold red]Invalid choice. Please try again.[/bold red]")
            await ainput("Press Enter to continue...")

    async def get_strategy_selection(self, prompt: str) -> Optional[Dict]:
        """
        Lists available strategies and prompts the user to select one by index.
        Returns the selected strategy dictionary or None if selection is invalid.
        """
        strategies = await self.strategy_manager.list_strategies()
        if not strategies:
            self.console.print("[bold red]No strategies found. Returning to main menu.[/bold red]")
            return None
        self.console.print("\n[bold cyan]--- Available Strategies ---[/bold cyan]")
        for idx, strat in enumerate(strategies, start=1):
            self.console.print(f"{idx}. {strat.get('title', 'N/A')} (ID: {strat.get('id', 'N/A')})")
        try:
            selection = (await ainput(f"{prompt} (Enter a number): ")).strip()
            index = int(selection) - 1
            if 0 <= index < len(strategies):
                return strategies[index]
            else:
                self.console.print("[bold red]Invalid selection. Returning to main menu.[/bold red]")
                return None
        except ValueError:
            self.console.print("[bold red]Invalid input. Please enter a valid number.[/bold red]")
            return None

    # ------------------ Menu Action Methods ------------------

    async def create_new_strategy(self):
        """Prompts the user to create a new strategy."""
        try:
            title = (await ainput("Enter the strategy title: ")).strip()
            description = (await ainput("Enter the strategy description: ")).strip()
            interpreter = StrategyInterpreter(os.getenv("OPENAI_API_KEY", ""))
            strategy_json = interpreter.interpret(description)
            strategy_id = await self.strategy_manager.save_strategy(title, description, strategy_json)
            self.console.print(f"[bold green]Strategy '{title}' created with ID: {strategy_id}.[/bold green]")
        except Exception as e:
            self.logger.error(f"Failed to create new strategy: {e}", exc_info=True)
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    async def edit_strategy(self):
        """Allows the user to edit an existing strategy."""
        try:
            strategy = await self.get_strategy_selection("Select a strategy to edit")
            if not strategy:
                return
            strategy_id = strategy.get("id")
            updates = {}
            new_title = (await ainput(f"New Title [{strategy.get('title', '')}]: ")).strip()
            if new_title:
                updates['title'] = new_title
            new_description = (await ainput(f"New Description [{strategy.get('description', '')}]: ")).strip()
            if new_description:
                updates['description'] = new_description
            await self.strategy_manager.edit_strategy(strategy_id, updates)
            self.console.print("[bold green]Strategy updated successfully.[/bold green]")
        except Exception as e:
            self.logger.error(f"Failed to edit strategy: {e}", exc_info=True)
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    async def list_strategies(self):
        """Lists all saved strategies in a formatted table with extended details."""
        try:
            strategies = await self.strategy_manager.list_strategies()
            if not strategies:
                self.console.print("[bold red]No strategies found.[/bold red]")
                return
            table = Table(title="Saved Strategies", title_style="bold cyan", expand=True)
            table.add_column("Option", justify="center", style="magenta", no_wrap=True)
            table.add_column("Title", style="cyan", overflow="fold")
            table.add_column("Description", style="green", overflow="fold")
            table.add_column("Rationale", style="yellow", overflow="fold")
            table.add_column("Assets", style="blue", overflow="fold")
            table.add_column("Trades", justify="center", style="red", no_wrap=True)
            
            for idx, strat in enumerate(strategies, start=1):
                title = strat.get("title", "N/A")
                description = strat.get("description", "N/A")
                rationale = strat.get("rationale", strat.get("strategy_rationale", "N/A"))
                assets = ", ".join(strat.get("assets", [])) if strat.get("assets") else "None"
                # Try to get trades from the strategy itself; otherwise, use TradeManager
                if "trades" in strat:
                    num_trades = str(len(strat.get("trades", [])))
                else:
                    trades_list = self.trade_manager.get_strategy_trades(strat.get("id"))
                    num_trades = str(len(trades_list))
                table.add_row(str(idx), title, description, rationale, assets, num_trades)
                
            self.console.print(table)
        except Exception as e:
            self.logger.error(f"Failed to list strategies: {e}", exc_info=True)
            self.console.print(f"[bold red]Error listing strategies: {e}[/bold red]")

    async def assign_budget(self):
        """Assigns a budget to a selected strategy."""
        try:
            strategy = await self.get_strategy_selection("Select a strategy to assign a budget")
            if not strategy:
                return
            strategy_id = strategy.get("id")
            amount_input = (await ainput("Enter the budget amount (in USDT): ")).strip()
            amount = float(amount_input)
            await self.budget_manager.set_budget(strategy_id, amount)
            self.console.print(f"[bold green]Budget of {amount:.2f} USDT assigned to strategy '{strategy.get('title')}'.[/bold green]")
        except Exception as e:
            self.logger.error(f"Failed to assign budget: {e}", exc_info=True)
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    async def activate_strategy(self):
        """Activates a selected strategy for live trading."""
        try:
            strategy = await self.get_strategy_selection("Select a strategy to activate")
            if not strategy:
                return
            strategy_id = strategy.get("id")
            budget = await self.budget_manager.get_budget(strategy_id)
            if budget <= 0:
                self.console.print(f"[bold red]No budget assigned to strategy '{strategy.get('title')}'. Please assign a budget first.[/bold red]")
                return
            await self.strategy_manager.activate_strategy_with_trades(strategy_id, budget)
            self.console.print(f"[bold green]Strategy '{strategy.get('title')}' activated successfully.[/bold green]")
        except Exception as e:
            self.logger.error(f"Failed to activate strategy: {e}", exc_info=True)
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    async def deactivate_strategy(self):
        """Deactivates a selected strategy."""
        try:
            strategy = await self.get_strategy_selection("Select a strategy to deactivate")
            if not strategy:
                return
            strategy_id = strategy.get("id")
            await self.strategy_manager.deactivate_strategy(strategy_id)
            self.console.print(f"[bold green]Strategy '{strategy.get('title')}' deactivated successfully.[/bold green]")
        except Exception as e:
            self.logger.error(f"Failed to deactivate strategy: {e}", exc_info=True)
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    async def remove_strategy(self):
        """Removes a selected strategy."""
        try:
            strategy = await self.get_strategy_selection("Select a strategy to remove")
            if not strategy:
                return
            strategy_id = strategy.get("id")
            await self.strategy_manager.remove_strategy(strategy_id)
            self.console.print("[bold green]Strategy removed successfully.[/bold green]")
        except Exception as e:
            self.logger.error(f"Failed to remove strategy: {e}", exc_info=True)
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    async def view_performance_metrics(self):
        """Displays performance metrics for a selected strategy."""
        try:
            strategy = await self.get_strategy_selection("Select a strategy to view performance")
            if not strategy:
                return
            strategy_id = strategy.get("id")
            metrics = self.performance_manager.calculate_summary(strategy_id)
            table = Table(title=f"Performance Metrics for '{strategy.get('title')}'")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="magenta")
            for key, value in metrics.items():
                table.add_row(key, str(value))
            self.console.print(table)
        except Exception as e:
            self.logger.error(f"Failed to view performance metrics: {e}", exc_info=True)
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    async def run_backtest(self):
        """Executes a backtest for a selected strategy."""
        try:
            strategy = await self.get_strategy_selection("Select a strategy to backtest")
            if not strategy:
                return
            strategy_id = strategy.get("id")
            self.console.print("\n[bold cyan]Select Data Source:[/bold cyan]")
            self.console.print("1. Synthetic Data")
            self.console.print("2. CSV File")
            self.console.print("3. Historical Data from Exchange (for strategy assets)")
            source_choice = (await ainput("Choose the data source (1/2/3): ")).strip()
            if not source_choice:
                return
            if source_choice == "1":
                scenario = (await ainput("Enter market scenario (bull, bear, sideways): ")).strip().lower()
                timeframe = (await ainput("Enter timeframe (e.g., 1m, 5m, 1h): ")).strip()
                duration_days = int((await ainput("Enter duration in days: ")).strip())
                historical_data = await self.backtester.generate_synthetic_data(
                    scenario=scenario, timeframe=timeframe, duration_days=duration_days
                )
            elif source_choice == "2":
                csv_path = (await ainput("Enter the path to the CSV file: ")).strip()
                try:
                    historical_data = pd.read_csv(csv_path)
                    self.console.print(f"[bold green]Loaded data from {csv_path}.[/bold green]")
                except Exception as e:
                    self.console.print(f"[bold red]Error loading CSV file: {e}[/bold red]")
                    return
            elif source_choice == "3":
                strategy_data = strategy.get("data", {})
                trading_pairs = strategy_data.get("assets", [])
                if not trading_pairs:
                    self.console.print("[bold red]No trading pairs found in the strategy.[/bold red]")
                    return
                self.console.print(f"[bold cyan]Fetching historical data for assets: {trading_pairs}[/bold cyan]")
                timeframe = (await ainput("Enter the timeframe (e.g., 1m, 5m, 1h): ")).strip()
                start_date = (await ainput("Enter the start date (YYYY-MM-DD): ")).strip()
                end_date = (await ainput("Enter the end date (YYYY-MM-DD): ")).strip()
                historical_data = await self.backtester._fetch_exchange_ohlcv_for_assets(
                    trading_pairs, timeframe, start_date, end_date
                )
                if historical_data.empty:
                    self.console.print("[bold red]No data fetched from the exchange.[/bold red]")
                    return
                self.console.print("[bold green]Fetched exchange data successfully.[/bold green]")
            else:
                self.console.print("[bold red]Invalid selection. Returning to main menu.[/bold red]")
                return
            results = await self.backtester.run_backtest(strategy_id, historical_data)
            self.console.print(f"[bold green]Backtest completed for '{strategy.get('title')}'[/bold green]")
            self.console.print(f"Initial Value: {results.get('initial_value', 0.0):.2f} USDT")
            self.console.print(f"Final Value: {results.get('final_value', 0.0):.2f} USDT")
            self.console.print(f"Total Return: {results.get('return', 0.0):.2f}%")
            self.console.print(f"Sharpe Ratio: {results.get('sharpe_ratio', 0.0):.2f}")
            self.console.print(f"Max Drawdown: {results.get('max_drawdown', 0.0):.2f}%")
            self.console.print(f"Win Rate: {results.get('win_rate', 0.0):.2f}%")
        except Exception as e:
            self.logger.error(f"Failed to run backtest: {e}", exc_info=True)
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    async def run_scenario_tests(self):
        """Prompts the user to run scenario tests on a selected strategy."""
        try:
            strategy = await self.get_strategy_selection("Select a strategy to run scenario tests")
            if not strategy:
                return
            strategy_id = strategy.get("id")
            self.console.print("\n[bold cyan]--- Select a Scenario ---[/bold cyan]")
            self.console.print("1. Bull Market")
            self.console.print("2. Bear Market")
            self.console.print("3. Sideways Market")
            self.console.print("4. High Volatility")
            self.console.print("5. Low Volatility")
            scenario_choice = (await ainput("Choose a scenario (Enter a number): ")).strip()
            scenarios = {
                "1": "bull",
                "2": "bear",
                "3": "sideways",
                "4": "high_volatility",
                "5": "low_volatility"
            }
            scenario = scenarios.get(scenario_choice)
            if not scenario:
                self.console.print("[bold red]Invalid choice. Returning to main menu.[/bold red]")
                return
            timeframe = (await ainput("Enter timeframe (e.g., 1m, 5m, 1h): ")).strip()
            duration_days = int((await ainput("Enter duration in days: ")).strip())
            synthetic_data = await self.backtester.generate_synthetic_data(
                scenario=scenario,
                timeframe=timeframe,
                duration_days=duration_days
            )
            results = await self.backtester.run_backtest(strategy_id, synthetic_data)
            self.console.print(f"[bold green]Scenario test complete. Results: {results}[/bold green]")
        except Exception as e:
            self.logger.error(f"Failed to run scenario tests: {e}", exc_info=True)
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    async def view_dashboard(self):
        """Launches the live trading dashboard."""
        try:
            self.console.print("[bold cyan]Launching the live trading dashboard...[/bold cyan]")
            await self.dashboard.start()
        except Exception as e:
            self.logger.error(f"Failed to display dashboard: {e}", exc_info=True)
            self.console.print(f"[bold red]Error: {e}[/bold red]")

    async def exit_program(self):
        """Exits the program gracefully."""
        self.console.print("[bold cyan]Exiting the program... Goodbye![/bold cyan]")
        await asyncio.sleep(1)
        os._exit(0)
