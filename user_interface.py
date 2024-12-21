import os
import logging
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.prompt import Prompt
from rich.progress import Progress
from strategy_manager import StrategyManager
from risk_manager import RiskManager
from budget_manager import BudgetManager
from performance_manager import PerformanceManager
from trade_monitor import TradeMonitor
from market_monitor import MarketMonitor
from backtester import Backtester
from synthetic_data_generator import generate_synthetic_data


class UserInterface:
    """
    Enhanced terminal-based interface for managing trading strategies, budgets, risk levels, and performance metrics.
    """

    def __init__(self, exchange):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.console = Console()
        self.strategy_manager = StrategyManager()
        self.risk_manager = RiskManager()
        self.budget_manager = BudgetManager()
        self.performance_manager = PerformanceManager()
        self.backtester = Backtester()
        self.market_monitor = MarketMonitor(exchange, self.strategy_manager, None)  # Placeholder for TradeExecutor
        self.trade_monitor = TradeMonitor(exchange, None, self.performance_manager)  # Placeholder for TradeManager

    def clear_screen(self):
        """Clear the terminal screen."""
        os.system("cls" if os.name == "nt" else "clear")

    def main(self):
        """
        Main loop for the user interface.
        """
        while True:
            self.clear_screen()
            layout = self.create_main_layout()
            self.console.print(layout)
            choice = Prompt.ask("[bold cyan]Enter your choice[/bold cyan]", choices=[str(i) for i in range(1, 11)], default="10")
            self.handle_menu_choice(choice)

    def create_main_layout(self):
        """Creates the main menu layout."""
        layout = Layout()
        layout.split_column(
            Layout(Panel("[bold cyan]Trading Bot Application[/bold cyan]", style="cyan"), size=3),
            Layout(self.create_menu_table(), size=12),
            Layout(Panel("[bold yellow]Navigate using numbers. Press 10 to exit.[/bold yellow]", style="yellow"), size=3),
        )
        return layout

    def create_menu_table(self):
        """Creates a rich table for the main menu."""
        table = Table(title="[bold magenta]Main Menu[/bold magenta]")
        table.add_column("Option", justify="center", style="cyan")
        table.add_column("Action", justify="left", style="magenta")

        options = [
            ("1", "Create New Strategy"),
            ("2", "Edit Existing Strategy"),
            ("3", "List All Strategies"),
            ("4", "Assign Budget to Strategy"),
            ("5", "Activate and Monitor Strategies"),
            ("6", "View Performance Metrics"),
            ("7", "Run Backtests"),
            ("8", "Show Live Dashboard"),
            ("9", "Manage Risk Levels"),
            ("10", "Exit Application"),
        ]
        for option in options:
            table.add_row(*option)
        return table

    def handle_menu_choice(self, choice):
        """
        Handles user input for the main menu.
        """
        menu_actions = {
            "1": self.create_new_strategy,
            "2": self.edit_strategy,
            "3": self.list_strategies,
            "4": self.assign_budget,
            "5": self.activate_and_monitor_strategies,
            "6": self.view_performance_metrics,
            "7": self.run_backtests,
            "8": self.show_live_dashboard,
            "9": self.manage_risk_levels,
            "10": self.exit_program,
        }
        action = menu_actions.get(choice)
        if action:
            action()
        else:
            self.console.print("[bold red]Invalid option selected. Returning to main menu...[/bold red]")

    def create_new_strategy(self):
        """Prompt user to create a new trading strategy."""
        self.clear_screen()
        try:
            title = Prompt.ask("Enter the strategy title")
            description = Prompt.ask("Enter the strategy description")

            from strategy_interpreter import StrategyInterpreter
            interpreter = StrategyInterpreter()
            strategy_data = interpreter.interpret(description)

            self.strategy_manager.save_strategy(title, description, strategy_data)
            self.console.print(f"[bold green]Strategy '{title}' created successfully![/bold green]")
        except Exception as e:
            self.logger.error(f"Failed to create a new strategy: {e}")
            self.console.print(f"[bold red]Error: {e}[/bold red]")
        input("Press Enter to return to the main menu...")

    def edit_strategy(self):
        """Allows the user to edit an existing strategy."""
        self.clear_screen()
        strategies = self.strategy_manager.list_strategies()
        if not strategies:
            self.console.print("[bold red]No strategies available to edit.[/bold red]")
            input("Press Enter to return to the main menu...")
            return

        strategy = self.select_strategy(strategies, "edit")
        if strategy:
            try:
                updates = {}
                title = Prompt.ask("Enter new title (leave blank to keep current)", default=strategy["title"])
                description = Prompt.ask("Enter new description (leave blank to keep current)", default=strategy["description"])
                if title != strategy["title"]:
                    updates["title"] = title
                if description != strategy["description"]:
                    updates["description"] = description

                self.strategy_manager.edit_strategy(strategy["id"], updates)
                self.console.print(f"[bold green]Strategy '{title}' updated successfully![/bold green]")
            except Exception as e:
                self.logger.error(f"Error editing strategy: {e}")
                self.console.print(f"[bold red]Error: {e}[/bold red]")
        input("Press Enter to return to the main menu...")

    def list_strategies(self):
        """Lists all available strategies."""
        self.clear_screen()
        strategies = self.strategy_manager.list_strategies()
        if not strategies:
            self.console.print("[bold red]No strategies available.[/bold red]")
            input("Press Enter to return to the main menu...")
            return

        table = Table(title="[bold cyan]Available Strategies[/bold cyan]")
        table.add_column("ID", justify="center", style="cyan")
        table.add_column("Title", style="magenta")
        table.add_column("Status", justify="center", style="green")

        for strategy in strategies:
            table.add_row(strategy["id"], strategy["title"], "[green]Active[/green]" if strategy["active"] else "[red]Inactive[/red]")

        self.console.print(table)
        input("Press Enter to return to the main menu...")

    def assign_budget(self):
        """Assigns a budget to a strategy."""
        self.clear_screen()
        strategies = self.strategy_manager.list_strategies()
        if not strategies:
            self.console.print("[bold red]No strategies available to assign budget.[/bold red]")
            input("Press Enter to return to the main menu...")
            return

        strategy = self.select_strategy(strategies, "assign budget")
        if strategy:
            try:
                budget = Prompt.ask("Enter the budget amount (in USDT)", default="100")
                self.budget_manager.set_budget(strategy["id"], float(budget))
                self.console.print(f"[bold green]Budget of {budget} USDT assigned to '{strategy['title']}'.[/bold green]")
            except Exception as e:
                self.logger.error(f"Error assigning budget: {e}")
                self.console.print(f"[bold red]Error: {e}[/bold red]")
        input("Press Enter to return to the main menu...")

    def show_live_dashboard(self):
        """Displays a live dashboard with active trades and strategies."""
        self.clear_screen()
        try:
            self.market_monitor.display_dashboard()
        except Exception as e:
            self.logger.error(f"Error displaying dashboard: {e}")
            self.console.print(f"[bold red]Error: {e}[/bold red]")
        input("Press Enter to return to the main menu...")

    def manage_risk_levels(self):
        """Allows the user to configure risk levels for strategies."""
        self.clear_screen()
        strategies = self.strategy_manager.list_strategies()
        if not strategies:
            self.console.print("[bold red]No strategies available to configure risk levels.[/bold red]")
            input("Press Enter to return to the main menu...")
            return

        strategy = self.select_strategy(strategies, "manage risk levels")
        if strategy:
            try:
                self.risk_manager.configure_risk(strategy["id"])
                self.console.print(f"[bold green]Risk levels configured for '{strategy['title']}'.[/bold green]")
            except Exception as e:
                self.logger.error(f"Error configuring risk levels: {e}")
                self.console.print(f"[bold red]Error: {e}[/bold red]")
        input("Press Enter to return to the main menu...")

    def select_strategy(self, strategies, action):
        """Helper method to select a strategy from a list."""
        table = Table(title=f"[bold cyan]Select a Strategy to {action}[/bold cyan]")
        table.add_column("Index", justify="center", style="cyan")
        table.add_column("Title", style="magenta")
        for idx, strategy in enumerate(strategies, 1):
            table.add_row(str(idx), strategy["title"])
        self.console.print(table)

        choice = Prompt.ask("Enter the index of the strategy", choices=[str(i) for i in range(1, len(strategies) + 1)])
        return strategies[int(choice) - 1]

    def exit_program(self):
        """Exit the application."""
        self.console.print("[bold cyan]Exiting the application. Goodbye![/bold cyan]")
        exit()
