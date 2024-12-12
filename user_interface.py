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
        # Initialize managers and interpreters
        self.strategy_manager = StrategyManager()
        self.budget_manager = BudgetManager()
        self.risk_manager = RiskManager()
        self.trade_manager = TradeManager()
        self.performance_manager = PerformanceManager()
        self.interpreter = StrategyInterpreter()

        # Set up exchange instances
        self.exchange = self.create_exchange_instance()
        self.monitor_exchange = self.create_exchange_instance()

        # Initialize trade and market monitors
        self.trade_executor = TradeExecutor(self.exchange, self.budget_manager, self.risk_manager, self.trade_manager)
        self.trade_monitor = TradeMonitor(self.monitor_exchange, self.trade_manager, self.performance_manager)
        self.market_monitor = MarketMonitor(self.monitor_exchange, self.strategy_manager, self.trade_executor)

        # Start background monitoring threads
        self.start_monitor_thread()

        # Logging and console
        self.logger = logging.getLogger(self.__class__.__name__)
        self.console = Console()

    def create_exchange_instance(self) -> ccxt.Exchange:
        """Create a CCXT Bitget exchange instance with API credentials."""
        return ccxt.bitget({
            'apiKey': BITGET_API_KEY,
            'secret': BITGET_SECRET,
            'password': BITGET_PASSWORD,
            'enableRateLimit': True,
        })

    def start_monitor_thread(self):
        """Start a background thread to handle monitoring tasks."""
        self.monitor_thread = threading.Thread(target=self.run_monitors, daemon=True)
        self.monitor_thread.start()

    def run_monitors(self):
        """Run the monitoring loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.start_monitoring_tasks())
        except asyncio.CancelledError:
            self.logger.info("Monitor thread was cancelled.")
        except Exception as e:
            self.logger.error(f"Error in monitor thread: {e}")
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

    async def start_monitoring_tasks(self):
        """Start monitoring tasks asynchronously."""
        tasks = [
            self.market_monitor.start_monitoring(),
            self.trade_monitor.start_monitoring(),
        ]
        await asyncio.gather(*tasks)

    @staticmethod
    def clear_screen():
        """Clear the terminal screen."""
        os.system('cls' if os.name == 'nt' else 'clear')

    @app.command()
    def main(self):
        """Main entry point for the user interface."""
        try:
            while True:
                self.clear_screen()
                self.display_header()
                choice = self.prompt_menu_selection()
                if not choice or choice == "12. Exit":
                    self.console.print("Exiting...")
                    asyncio.run(self.close_exchanges())
                    break
                self.handle_menu_choice(choice)
        except KeyboardInterrupt:
            self.console.print("\n[bold yellow]Interrupted by user. Exiting...[/bold yellow]")
            asyncio.run(self.close_exchanges())

    def prompt_menu_selection(self) -> str:
        """Prompt the user to select an option from the main menu."""
        return self.prompt_questionary(
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

    def handle_menu_choice(self, choice: str):
        """Handle the user's menu selection."""
        choice_number = choice.split('.')[0]
        menu_actions = {
            "1": self.create_new_strategy,
            "2": self.load_strategy,
            "3": self.edit_strategy,
            "4": self.define_risk_parameters,
            "5": self.define_budget,
            "6": self.activate_strategy,
            "7": self.view_active_strategies,
            "8": self.view_performance,
            "9": self.test_strategy,
            "10": self.suggest_strategy,
            "11": self.cancel_strategy,
        }
        action = menu_actions.get(choice_number)
        if action:
            action()
        else:
            self.console.print("[bold red]Invalid choice. Please try again.[/bold red]")

    def display_header(self):
        """Display the application header."""
        header_text = Text("Welcome to AI Crypto Strategy Manager", style="bold cyan")
        header_panel = Panel(header_text, style="bold white on purple", expand=False)
        self.console.print(header_panel, justify="center")

    def prompt_questionary(self, prompt_func, *args, **kwargs):
        """Handle user input using Questionary."""
        try:
            response = prompt_func(*args, **kwargs).ask()
            if response is None:
                self.console.print("[bold yellow]Operation cancelled. Returning to main menu.[/bold yellow]")
                time.sleep(1)
            return response
        except KeyboardInterrupt:
            self.console.print("\n[bold yellow]Interrupted by user. Returning to main menu.[/bold yellow]")
            time.sleep(1)
            return None

    async def close_exchanges(self):
        """Close exchange connections gracefully."""
        for exchange in [self.exchange, self.monitor_exchange]:
            try:
                await exchange.close()
                self.logger.info(f"{exchange.name} exchange closed.")
            except Exception as e:
                self.logger.error(f"Error closing {exchange.name} exchange: {e}")
