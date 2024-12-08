# user_interface.py

import threading
import logging
import os
import json
import asyncio
import time

import typer
import ccxt.async_support as ccxt
import questionary
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from typing import Dict, List

from strategy_interpreter import StrategyInterpreter
from strategy_manager import StrategyManager
from budget_manager import BudgetManager
from risk_manager import RiskManager
from trade_executor import TradeExecutor
from trade_manager import TradeManager
from performance_manager import PerformanceManager
from trade_monitor import TradeMonitor
from market_monitor import MarketMonitor
from backtester import Backtester
import pandas as pd
from config import BITGET_API_KEY, BITGET_SECRET, BITGET_PASSWORD

app = typer.Typer()


class UserInterface:
    def __init__(self):
        self.strategy_manager = StrategyManager()
        self.budget_manager = BudgetManager()
        self.risk_manager = RiskManager()
        self.trade_manager = TradeManager()
        self.performance_manager = PerformanceManager()
        self.interpreter = StrategyInterpreter()

        # Main exchange instance for main thread operations
        self.exchange = ccxt.bitget({
            'apiKey': BITGET_API_KEY,
            'secret': BITGET_SECRET,
            'password': BITGET_PASSWORD,
            'enableRateLimit': True,
        })

        # Separate exchange instance for monitor thread
        self.monitor_exchange = ccxt.bitget({
            'apiKey': BITGET_API_KEY,
            'secret': BITGET_SECRET,
            'password': BITGET_PASSWORD,
            'enableRateLimit': True,
        })

        self.trade_executor = TradeExecutor(
            self.exchange,
            self.budget_manager,
            self.risk_manager,
            self.trade_manager
        )

        self.trade_monitor = TradeMonitor(
            self.monitor_exchange,  # Use monitor_exchange here
            self.trade_manager,
            self.performance_manager
        )
        self.market_monitor = MarketMonitor(
            self.monitor_exchange,  # Use monitor_exchange here
            self.strategy_manager,
            self.trade_executor
        )
        self.monitor_thread = threading.Thread(target=self.start_monitors)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        self.console = Console()
        self.logger = logging.getLogger(self.__class__.__name__)

    def start_monitors(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        tasks = [
            self.market_monitor.start_monitoring(),
            self.trade_monitor.start_monitoring()
        ]
        try:
            loop.run_until_complete(asyncio.gather(*tasks))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Error in monitor thread: {e}")
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

    def prompt_questionary(self, prompt_func, *args, **kwargs):
        """
        A helper method to handle questionary prompts.
        
        Args:
            prompt_func: The questionary prompt function (e.g., questionary.text, questionary.select).
            *args: Positional arguments for the prompt function.
            **kwargs: Keyword arguments for the prompt function.
        
        Returns:
            The user's response or None if Esc was pressed.
        """
        try:
            response = prompt_func(*args, **kwargs).ask()
            if response is None:
                # User pressed Esc; return to main menu
                self.console.print("[bold yellow]Operation cancelled. Returning to main menu.[/bold yellow]")
                time.sleep(1)
                return None
            return response
        except KeyboardInterrupt:
            # Handle Ctrl+C gracefully
            self.console.print("\n[bold yellow]Interrupted by user. Returning to main menu.[/bold yellow]")
            time.sleep(1)
            return None

    @app.command()
    def main(self):
        try:
            while True:
                os.system('cls' if os.name == 'nt' else 'clear')
                self.display_header()
                choice = self.prompt_questionary(
                    questionary.select,
                    "Select an option:",
                    choices=[
                        "1. Create New Strategy",
                        "2. Load Strategy",
                        "3. Edit Strategy",
                        "4. Define Risk Parameters",
                        "5. Define Budget",
                        "6. Activate Strategy",
                        "7. View Active Strategies",
                        "8. View Performance Metrics",
                        "9. Test Strategy",
                        "10. Suggest a Strategy",
                        "11. Cancel Strategy",
                        "12. Exit"
                    ]
                )
                if choice is None or choice == "12. Exit":
                    self.console.print("Exiting...")
                    # Close both exchange instances before exiting
                    asyncio.run(self.close_exchanges())
                    break
                choice_number = choice.split('.')[0]
                if choice_number == "1":
                    self.create_new_strategy()
                elif choice_number == "2":
                    self.load_strategy()
                elif choice_number == "3":
                    self.edit_strategy()
                elif choice_number == "4":
                    self.define_risk_parameters()
                elif choice_number == "5":
                    self.define_budget()
                elif choice_number == "6":
                    self.activate_strategy()
                elif choice_number == "7":
                    self.view_active_strategies()
                elif choice_number == "8":
                    self.view_performance()
                elif choice_number == "9":
                    self.test_strategy()
                elif choice_number == "10":
                    self.suggest_strategy()
                elif choice_number == "11":
                    self.cancel_strategy()
                else:
                    self.console.print("[bold red]Invalid choice. Please try again.[/bold red]")
                # Prompt to press Enter to continue
                self.prompt_questionary(questionary.text, "Press Enter to continue.")
        except KeyboardInterrupt:
            self.console.print("\n[bold yellow]Interrupted by user. Exiting...[/bold yellow]")
            asyncio.run(self.close_exchanges())

    def display_header(self):
        header_text = Text("Welcome to AI Crypto Strategy Manager", style="bold cyan")
        header_panel = Panel(header_text, style="bold white on purple", expand=False)
        self.console.print(header_panel, justify="center")

    def display_menu(self):
        menu_options = [
            ("1", "Create New Strategy"),
            ("2", "Load Strategy"),
            ("3", "Edit Strategy"),
            ("4", "Define Risk Parameters"),
            ("5", "Define Budget"),
            ("6", "Activate Strategy"),
            ("7", "View Active Strategies"),
            ("8", "View Performance Metrics"),
            ("9", "Test Strategy"),
            ("10", "Suggest a Strategy"),
            ("11", "Cancel Strategy"),
            ("12", "Exit"),
        ]
        menu_table = Table(title="Main Menu", show_header=False, box=box.SQUARE)
        menu_table.add_column("Option", style="bold cyan", width=6)
        menu_table.add_column("Description", style="bold white")
        for option, description in menu_options:
            menu_table.add_row(option, description)
        self.console.print(menu_table)

    def create_new_strategy(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        self.console.print(Panel("[bold magenta]Create New Strategy[/bold magenta]", expand=False))

        # Prompt for strategy description
        description = self.prompt_questionary(questionary.text, "Enter your trading strategy description:")
        if description is None:
            return  # Already handled in helper

        # Use the interpreter to generate strategy details
        while True:
            try:
                strategy_data = self.interpreter.interpret(description)
                break
            except ValueError as e:
                self.console.print(f"[bold red]Error:[/bold red] {e}")
                description = self.prompt_questionary(
                    questionary.text,
                    "Please provide the missing details or correct the description:"
                )
                if description is None:
                    return  # Already handled

        # Prompt for a strategy title
        title = self.prompt_questionary(questionary.text, "Enter a title for your strategy:")
        if not title:
            self.console.print("[bold red]Strategy title cannot be empty.[/bold red]")
            time.sleep(1)
            return

        # Prompt for the risk level
        risk_level = self.prompt_questionary(
            questionary.select,
            "Enter your desired risk level:",
            choices=["low", "medium", "high"]
        )
        if risk_level is None:
            return  # Already handled

        # Suggest risk parameters and add to strategy data
        suggested_risk = self.risk_manager.suggest_risk_parameters(risk_level)
        strategy_data['risk_management'] = suggested_risk

        # Save the strategy
        try:
            strategy_id = self.strategy_manager.save_strategy(title, description, strategy_data)
            self.console.print(f"[bold cyan]Strategy '{title}' saved successfully with ID '{strategy_id}'.[/bold cyan]")
            time.sleep(1)
        except Exception as e:
            self.console.print(f"[bold red]Failed to save strategy: {e}[/bold red]")
            time.sleep(1)

    def load_strategy(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        self.console.print(Panel("[bold magenta]Load Strategy[/bold magenta]", expand=False))
        strategies = self.strategy_manager.list_strategies()
        if not strategies:
            self.console.print("[bold yellow]No strategies found.[/bold yellow]")
            time.sleep(1)
            return
        # Display strategies with titles and IDs
        strategy_choices = [f"{s['title']} (ID: {s['id']})" for s in strategies]
        strategy_choice = self.prompt_questionary(
            questionary.select,
            "Select a strategy to load:",
            choices=strategy_choices
        )
        if strategy_choice is None:
            return  # Already handled

        # Extract ID from the selected choice
        strategy_id = strategy_choice.split("ID: ")[1].strip(")")
        try:
            strategy_record = self.strategy_manager.load_strategy(strategy_id)
            self.console.print(f"[bold cyan]Strategy '{strategy_record['title']}' loaded successfully.[/bold cyan]")
            self.console.print(json.dumps(strategy_record['data'], indent=2))
            time.sleep(1)
        except ValueError as e:
            self.console.print(f"[bold red]{e}[/bold red]")
            time.sleep(1)

    def edit_strategy(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        self.console.print(Panel("[bold magenta]Edit Strategy[/bold magenta]", expand=False))
        strategies = self.strategy_manager.list_strategies()
        if not strategies:
            self.console.print("[bold yellow]No strategies found.[/bold yellow]")
            time.sleep(1)
            return
        strategy_choices = [f"{s['title']} (ID: {s['id']})" for s in strategies]
        strategy_choice = self.prompt_questionary(
            questionary.select,
            "Select a strategy to edit:",
            choices=strategy_choices
        )
        if strategy_choice is None:
            return  # Already handled
        strategy_id = strategy_choice.split("ID: ")[1].strip(")")
        try:
            strategy_record = self.strategy_manager.load_strategy(strategy_id)
            self.edit_strategy_parameters(strategy_id, strategy_record)
        except ValueError as e:
            self.console.print(f"[bold red]{e}[/bold red]")
            time.sleep(1)

    def edit_strategy_parameters(self, strategy_id: str, strategy_record: Dict):
        self.console.print(f"[bold cyan]Editing strategy '{strategy_record['title']}' (ID: {strategy_id}).[/bold cyan]")
        strategy_data = strategy_record['data']
        title = self.prompt_questionary(
            questionary.text,
            f"Enter new title (current: '{strategy_record['title']}'), or press Enter to keep unchanged:",
            default=str(strategy_record['title'])
        )
        if title is None:
            return  # Already handled
        description = self.prompt_questionary(
            questionary.text,
            f"Enter new description, or press Enter to keep unchanged:",
            default=str(strategy_record['description'])
        )
        if description is None:
            return  # Already handled

        for key in list(strategy_data.keys()):
            if key == 'strategy_name':
                continue
            elif isinstance(strategy_data[key], dict):
                self.edit_sub_parameters(key, strategy_data[key])
            elif isinstance(strategy_data[key], list):
                self.edit_list_parameter(key, strategy_data[key])
            else:
                new_value = self.prompt_questionary(
                    questionary.text,
                    f"Enter value for '{key}' (current: '{strategy_data[key]}'), or press Enter to keep unchanged:",
                    default=str(strategy_data[key])
                )
                if new_value == '':
                    continue
                if new_value is None:
                    return  # Already handled
                strategy_data[key] = self.convert_value(new_value, strategy_data[key])

        confirm = self.prompt_questionary(
            questionary.confirm,
            "Do you want to save the changes?"
        )
        if confirm is None or not confirm:
            self.console.print("[bold yellow]Changes discarded.[/bold yellow]")
            time.sleep(1)
            return
        try:
            self.strategy_manager.update_strategy(strategy_id, title, description, strategy_data)
            self.console.print(f"[bold green]Strategy '{title}' updated successfully.[/bold green]")
            time.sleep(1)
        except Exception as e:
            self.console.print(f"[bold red]Failed to update strategy: {e}[/bold red]")
            time.sleep(1)

    def edit_sub_parameters(self, parent_key: str, sub_dict: Dict):
        self.console.print(f"\n[bold magenta]{parent_key.upper()}[/bold magenta]")
        for key in list(sub_dict.keys()):
            if isinstance(sub_dict[key], dict):
                self.edit_sub_parameters(f"{parent_key}.{key}", sub_dict[key])
            elif isinstance(sub_dict[key], list):
                self.edit_list_parameter(f"{parent_key}.{key}", sub_dict[key])
            else:
                new_value = self.prompt_questionary(
                    questionary.text,
                    f"Enter value for '{parent_key}.{key}' (current: '{sub_dict[key]}'), or press Enter to keep unchanged:",
                    default=str(sub_dict[key])
                )
                if new_value == '':
                    continue
                if new_value is None:
                    return  # Already handled
                sub_dict[key] = self.convert_value(new_value, sub_dict[key])

    def edit_list_parameter(self, key: str, value_list: list):
        self.console.print(f"\n[bold magenta]{key.upper()}[/bold magenta]")
        self.console.print(f"Current values: {value_list}")
        action = self.prompt_questionary(
            questionary.select,
            f"What would you like to do with '{key}'?",
            choices=[
                "Add Item",
                "Remove Item",
                "Edit Item",
                "Keep Unchanged",
                "Cancel Editing"
            ]
        )
        if action is None:
            return  # Already handled
        if action == "Add Item":
            new_item = self.prompt_questionary(
                questionary.text,
                f"Enter new item to add to '{key}':"
            )
            if new_item:
                value_list.append(new_item)
        elif action == "Remove Item":
            if not value_list:
                self.console.print("[bold yellow]List is empty. Nothing to remove.[/bold yellow]")
                time.sleep(1)
                return
            item_to_remove = self.prompt_questionary(
                questionary.select,
                f"Select an item to remove from '{key}':",
                choices=value_list
            )
            if item_to_remove:
                value_list.remove(item_to_remove)
        elif action == "Edit Item":
            if not value_list:
                self.console.print("[bold yellow]List is empty. Nothing to edit.[/bold yellow]")
                time.sleep(1)
                return
            item_to_edit = self.prompt_questionary(
                questionary.select,
                f"Select an item to edit in '{key}':",
                choices=value_list
            )
            if item_to_edit:
                new_value = self.prompt_questionary(
                    questionary.text,
                    f"Enter new value for '{item_to_edit}':",
                    default=item_to_edit
                )
                if new_value:
                    index = value_list.index(item_to_edit)
                    value_list[index] = new_value
        elif action == "Keep Unchanged":
            pass
        elif action == "Cancel Editing":
            self.console.print("[bold yellow]Editing cancelled.[/bold yellow]")
            time.sleep(1)

    def convert_value(self, new_value, old_value):
        try:
            if isinstance(old_value, int):
                return int(new_value)
            elif isinstance(old_value, float):
                return float(new_value)
            elif isinstance(old_value, bool):
                return new_value.lower() in ['true', 'yes', '1']
            else:
                return new_value
        except ValueError:
            self.console.print(f"[bold red]Invalid input. Expected type {type(old_value).__name__}. Keeping original value.[/bold red]")
            time.sleep(1)
            return old_value

    def define_risk_parameters(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        self.console.print(Panel("[bold magenta]Define Risk Parameters[/bold magenta]", expand=False))
        strategies = self.strategy_manager.list_strategies()
        if not strategies:
            self.console.print("[bold yellow]No strategies found.[/bold yellow]")
            time.sleep(1)
            return
        strategy_choices = [f"{s['title']} (ID: {s['id']})" for s in strategies]
        strategy_choice = self.prompt_questionary(
            questionary.select,
            "Select a strategy to define risk parameters for:",
            choices=strategy_choices
        )
        if strategy_choice is None:
            return  # Already handled
        strategy_id = strategy_choice.split("ID: ")[1].strip(")")
        risk_level = self.prompt_questionary(
            questionary.select,
            "Enter your desired risk level:",
            choices=["low", "medium", "high"]
        )
        if risk_level is None:
            return  # Already handled
        try:
            risk_params = self.risk_manager.suggest_risk_parameters(risk_level)
            self.strategy_manager.update_risk_parameters(strategy_id, risk_params)
            self.console.print(f"[bold cyan]Risk parameters for strategy ID '{strategy_id}' updated.[/bold cyan]")
            time.sleep(1)
        except ValueError as e:
            self.console.print(f"[bold red]{e}[/bold red]")
            time.sleep(1)

    def define_budget(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        self.console.print(Panel("[bold magenta]Define Budget[/bold magenta]", expand=False))
        strategies = self.strategy_manager.list_strategies()
        if not strategies:
            self.console.print("[bold yellow]No strategies found.[/bold yellow]")
            time.sleep(1)
            return
        strategy_choices = [f"{s['title']} (ID: {s['id']})" for s in strategies]
        strategy_choice = self.prompt_questionary(
            questionary.select,
            "Select a strategy to define budget for:",
            choices=strategy_choices
        )
        if strategy_choice is None:
            return  # Already handled
        strategy_id = strategy_choice.split("ID: ")[1].strip(")")
        budget = self.prompt_questionary(
            questionary.text,
            "Enter your budget for this strategy:"
        )
        if budget is None:
            return  # Already handled
        try:
            budget = float(budget)
            self.budget_manager.set_budget(strategy_id, budget)
            self.console.print(f"[bold cyan]Budget for strategy ID '{strategy_id}' set to {budget}.[/bold cyan]")
            time.sleep(1)
        except ValueError:
            self.console.print("[bold red]Invalid budget amount.[/bold red]")
            time.sleep(1)

    def activate_strategy(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        self.console.print(Panel("[bold magenta]Activate Strategy[/bold magenta]", expand=False))
        strategies = self.strategy_manager.list_strategies()
        if not strategies:
            self.console.print("[bold yellow]No strategies found.[/bold yellow]")
            time.sleep(1)
            return
        strategy_choices = [f"{s['title']} (ID: {s['id']})" for s in strategies]
        strategy_choice = self.prompt_questionary(
            questionary.select,
            "Select a strategy to activate:",
            choices=strategy_choices
        )
        if strategy_choice is None:
            return  # Already handled
        strategy_id = strategy_choice.split("ID: ")[1].strip(")")
        if not self.strategy_manager.is_strategy_complete(strategy_id):
            self.console.print(f"[bold red]Strategy ID '{strategy_id}' is incomplete and cannot be activated.[/bold red]")
            time.sleep(1)
            return
        try:
            self.strategy_manager.activate_strategy(strategy_id)
            self.console.print(f"[bold cyan]Strategy ID '{strategy_id}' activated.[/bold cyan]")
            time.sleep(1)
        except Exception as e:
            self.console.print(f"[bold red]Failed to activate strategy: {e}[/bold red]")
            time.sleep(1)

    def view_active_strategies(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        self.console.print(Panel("[bold magenta]View Active Strategies[/bold magenta]", expand=False))
        strategies = self.strategy_manager.get_active_strategies()
        if not strategies:
            self.console.print("[bold yellow]No active strategies.[/bold yellow]")
            return
        strategy_table = Table(title="Active Strategies", show_header=True, header_style="bold magenta")
        strategy_table.add_column("Strategy ID", style="bold cyan")
        strategy_table.add_column("Title", style="bold white")
        strategy_table.add_column("Description", style="bold white")
        for strategy in strategies:
            strategy_id = strategy['id']
            title = strategy['title']
            description = strategy['strategy_data'].get('description', 'No description')
            strategy_table.add_row(strategy_id, title, description)
        self.console.print(strategy_table)

    def view_performance(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        self.console.print(Panel("[bold magenta]View Performance Metrics[/bold magenta]", expand=False))
        strategies = self.strategy_manager.list_strategies()
        if not strategies:
            self.console.print("[bold yellow]No strategies found.[/bold yellow]")
            time.sleep(1)
            return
        strategy_choices = [f"{s['title']} (ID: {s['id']})" for s in strategies]
        strategy_choice = self.prompt_questionary(
            questionary.select,
            "Select a strategy to view performance:",
            choices=strategy_choices
        )
        if strategy_choice is None:
            return  # Already handled
        strategy_id = strategy_choice.split("ID: ")[1].strip(")")
        self.display_performance_metrics(strategy_id)

    def display_performance_metrics(self, strategy_id: str):
        performance_data = self.performance_manager.get_performance_data(strategy_id)
        if not performance_data:
            self.console.print(f"[bold yellow]No performance data available for strategy ID '{strategy_id}'.[/bold yellow]")
            time.sleep(1)
            return

        table = Table(title=f"Performance Metrics for Strategy ID '{strategy_id}'", show_header=True, header_style="bold magenta")
        table.add_column("Date", style="dim", width=12)
        table.add_column("Total P&L", justify="right")
        table.add_column("ROI (%)", justify="right")
        table.add_column("Win Rate (%)", justify="right")
        table.add_column("Avg Profit per Trade", justify="right")
        table.add_column("Max Drawdown (%)", justify="right")

        for data_point in performance_data:
            table.add_row(
                data_point['date'],
                f"{data_point['total_pnl']:.2f}",
                f"{data_point['roi']:.2f}",
                f"{data_point['win_rate']:.2f}",
                f"{data_point['avg_profit']:.2f}",
                f"{data_point['max_drawdown']:.2f}"
            )
        self.console.print(table)
        time.sleep(1)

    def test_strategy(self):

        os.system('cls' if os.name == 'nt' else 'clear')
        self.console.print(Panel("[bold magenta]Test Strategy[/bold magenta]", expand=False))
        strategies = self.strategy_manager.list_strategies()
        if not strategies:
            self.console.print("[bold yellow]No strategies found.[/bold yellow]")
            time.sleep(3)
            return

        strategy_choices = [f"{s['title']} (ID: {s['id']})" for s in strategies]
        strategy_choice = self.prompt_questionary(
            questionary.select,
            "Select a strategy to test:",
            choices=strategy_choices
        )
        if strategy_choice is None:
            return  # Already handled

        strategy_id = strategy_choice.split("ID: ")[1].strip(")")

        try:
            # Load the strategy details
            strategy_record = self.strategy_manager.load_strategy(strategy_id)
            strategy_data = strategy_record['data']
            asset = strategy_data['assets'][0]  # Assuming at least one asset is always present

            # Extract market type dynamically
            market_type = strategy_data.get('market_type')
            if not market_type:
                self.console.print("[bold red]Market type is missing from the strategy data.[/bold red]")
                return

            # Ask user for timeframe and data limit
            timeframe = self.prompt_questionary(
                questionary.text,
                "Enter the timeframe to test (e.g., 1d, 1h, 15m):",
                default='1d'
            )
            if timeframe is None:
                return  # Already handled
            limit = self.prompt_questionary(
                questionary.text,
                "Enter the number of data points to fetch:",
                default='365'
            )
            if limit is None:
                return  # Already handled
            try:
                limit = int(limit)
            except ValueError:
                self.console.print("[bold red]Invalid number of data points.[/bold red]")
                time.sleep(3)
                return

            # Attempt to fetch real historical data
            try:
                historical_data = asyncio.run(self.fetch_historical_data(
                    asset=asset,
                    timeframe=timeframe,
                    limit=limit,
                    market_type=market_type
                ))
            except Exception as e:
                self.console.print(f"[bold red]Error fetching historical data:[/bold red] {e}")
                # Prompt to use dummy data instead
                choice = self.prompt_questionary(
                    questionary.confirm,
                    "Do you want to use dummy data instead?",
                    default=False
                )
                if choice:
                    historical_data = self.create_dummy_data()
                else:
                    self.console.print("[bold red]Cannot proceed without data.[/bold red]")
                    time.sleep(3)
                    return

            # Pass historical data to the backtester
            backtester = Backtester()
            backtester.run_backtest(strategy_data, historical_data)
            self.console.print("[bold green]Backtest completed successfully.[/bold green]")
            time.sleep(3)

        except ValueError as e:
            self.console.print(f"[bold red]{e}[/bold red]")

    async def fetch_historical_data(self, asset: str, timeframe: str = '1d', limit: int = 365, market_type: str = 'spot') -> pd.DataFrame:
        """
        Fetches historical OHLCV data for the specified market type.

        Args:
            asset (str): The trading pair or symbol.
            timeframe (str): The timeframe to fetch data for (e.g., '1d', '1h').
            limit (int): The number of data points to fetch.
            market_type (str): The type of market (e.g., 'spot', 'futures', 'margin').

        Returns:
            pd.DataFrame: A DataFrame containing the historical data.
        """
        try:
            await self.exchange.load_markets()
            ohlcv = await self.exchange.fetch_ohlcv(
                symbol=asset,
                timeframe=timeframe,
                limit=limit,
                params={'type': market_type}  # Use the market type dynamically
            )
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('datetime', inplace=True)
            return df
        except Exception as e:
            self.logger.error(f"Failed to fetch historical data: {e}")
            self.console.print(f"[bold red]Failed to fetch historical data: {e}[/bold red]")
            time.sleep(3)
            raise

    def create_dummy_data(self) -> pd.DataFrame:
        self.console.print("[bold yellow]Creating dummy data for backtesting...[/bold yellow]")
        date_range = pd.date_range(end=pd.Timestamp.now(), periods=100, freq='D')
        data = {
            'open': pd.Series([100 + i * 0.5 for i in range(len(date_range))]),
            'high': pd.Series([101 + i * 0.5 for i in range(len(date_range))]),
            'low': pd.Series([99 + i * 0.5 for i in range(len(date_range))]),
            'close': pd.Series([100 + i * 0.5 for i in range(len(date_range))]),
            'volume': pd.Series([1000 + i * 10 for i in range(len(date_range))]),
        }
        df = pd.DataFrame(data, index=date_range)
        df.index.name = 'datetime'
        return df

    def suggest_strategy(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        self.console.print(Panel("[bold magenta]Suggest a Strategy[/bold magenta]", expand=False))
        risk_levels = ['safe', 'standard', 'medium', 'high risk', 'aggressive', 'insane', 'god mode']
        risk_level = self.prompt_questionary(
            questionary.select,
            "Enter your desired risk level:",
            choices=risk_levels
        )
        if risk_level is None:
            return  # Already handled

        market_types = {'1': 'spot', '2': 'futures', '3': 'margin'}
        market_choice = self.prompt_questionary(
            questionary.select,
            "Select Market Type:",
            choices=[
                "1. Spot",
                "2. Futures",
                "3. Margin"
            ]
        )
        if market_choice is None:
            return  # Already handled
        market_type = market_types.get(market_choice.split('.')[0])

        self.console.print(f"{market_type.capitalize()} Market and {risk_level.capitalize()} Risk Level selected.")

        # Step 3: Generate Strategy Using GPT
        try:
            strategy_data = self.interpreter.suggest_strategy(risk_level, market_type)
        except ValueError as e:
            self.console.print(f"[bold red]Error generating strategy: {e}[/bold red]")
            choice = self.prompt_questionary(
                questionary.confirm,
                "Do you want to try again?",
                default=False
            )
            if choice:
                self.suggest_strategy()
            return
        except Exception as e:
            self.console.print(f"[bold red]An unexpected error occurred: {e}[/bold red]")
            time.sleep(3)
            return

        # Display strategy for user review
        strategy_json = json.dumps(strategy_data, indent=2)
        self.console.print(Panel(f"[bold green]Suggested Strategy Details:[/bold green]\n{strategy_json}", expand=False))

        # Prompt for Strategy Title
        title = self.prompt_questionary(
            questionary.text,
            "Enter a title for your suggested strategy:"
        )
        if not title:
            self.console.print("[bold red]Strategy title cannot be empty.[/bold red]")
            time.sleep(3)
            return

        # Save the suggested strategy
        description = f"Automatically suggested strategy for risk level '{risk_level}' and market type '{market_type}'."
        try:
            strategy_id = self.strategy_manager.save_strategy(title, description, strategy_data)
            self.console.print(f"[bold cyan]Strategy '{title}' saved successfully with ID '{strategy_id}'.[/bold cyan]")
            time.sleep(1)
        except Exception as e:
            self.console.print(f"[bold red]Failed to save suggested strategy: {e}[/bold red]")
            time.sleep(3)

    async def close_exchanges(self):
        # Close both exchange instances gracefully
        try:
            await self.exchange.close()
            self.logger.info("Main exchange closed.")
        except Exception as e:
            self.logger.error(f"Error closing main exchange: {e}")

        try:
            await self.monitor_exchange.close()
            self.logger.info("Monitor exchange closed.")
        except Exception as e:
            self.logger.error(f"Error closing monitor exchange: {e}")

    def cancel_strategy(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        self.console.print(Panel("[bold magenta]Cancel Strategy[/bold magenta]", expand=False))
        strategies = self.strategy_manager.list_strategies()
        if not strategies:
            self.console.print("[bold yellow]No strategies found.[/bold yellow]")
            time.sleep(1)
            return
        strategy_choices = [f"{s['title']} (ID: {s['id']})" for s in strategies]
        strategy_choice = self.prompt_questionary(
            questionary.select,
            "Select a strategy to cancel:",
            choices=strategy_choices
        )
        if strategy_choice is None:
            return  # Already handled
        strategy_id = strategy_choice.split("ID: ")[1].strip(")")
        confirm = self.prompt_questionary(
            questionary.confirm,
            f"Are you sure you want to cancel and remove strategy '{strategy_id}'?"
        )
        if confirm is None or not confirm:
            self.console.print("[bold yellow]Cancellation aborted.[/bold yellow]")
            time.sleep(3)
            return
        try:
            self.cancel_all_trades(strategy_id)
            self.console.print(f"[bold cyan]Strategy ID '{strategy_id}' has been canceled and removed.[/bold cyan]")
            time.sleep(3)
        except Exception as e:
            self.console.print(f"[bold red]Failed to cancel strategy: {e}[/bold red]")
            time.sleep(3)

    def cancel_all_trades(self, strategy_id: str):
        trades = self.trade_manager.get_trades_by_strategy(strategy_id)
        for trade in trades:
            if trade['status'] == 'open':
                try:
                    asyncio.run(self.exchange.cancel_order(
                        trade['order_id'],
                        trade['asset'],
                        params={'type': trade.get('market_type', 'spot')}
                    ))
                    self.trade_manager.update_trade(trade['order_id'], {'status': 'canceled'})
                    self.logger.info(f"Canceled trade '{trade['order_id']}' for strategy ID '{strategy_id}'.")
                    time.sleep(3)
                except Exception as e:
                    self.logger.error(f"Failed to cancel trade '{trade['order_id']}': {e}")
                    time.sleep(3)
        try:
            self.strategy_manager.deactivate_strategy(strategy_id)
            self.strategy_manager.remove_strategy(strategy_id)
            self.budget_manager.remove_budget(strategy_id)
            self.performance_manager.clear_performance_data(strategy_id)
            self.logger.info(f"Strategy ID '{strategy_id}' and all associated data have been removed.")
            time.sleep(3)
        except Exception as e:
            self.logger.error(f"Failed to remove strategy ID '{strategy_id}': {e}")
            time.sleep(3)
