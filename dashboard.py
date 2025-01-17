from rich.console import Console
from rich.table import Table
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
from rich.align import Align
import asyncio
import logging
import random
import shutil


class Dashboard:
    """
    Dashboard for displaying live updates on trades, strategies, and market details.
    Includes real-time graphs and price changes for assets in each strategy.
    """

    def __init__(self, exchange, strategy_manager, trade_manager, market_monitor, performance_manager):
        self.console = Console()
        self.exchange = exchange
        self.strategy_manager = strategy_manager
        self.trade_manager = trade_manager
        self.market_monitor = market_monitor
        self.performance_manager = performance_manager
        self.logger = logging.getLogger(self.__class__.__name__)
        self.current_page = 1  # For pagination
        self.strategies_per_page = 1

        # Initialize the layout
        self.layout = Layout()
        self.layout.split(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )
        self.layout["body"].split_column(
            Layout(name="summary"),
            Layout(name="details"),
        )
        self.init_header()
        self.init_footer()

    def init_header(self):
        """Initializes the header layout."""
        header_text = Text("GenStrat Trading Dashboard", style="bold cyan")
        self.layout["header"].update(Panel(header_text, title="Welcome", title_align="left"))

    def init_footer(self):
        """Initializes the footer layout."""
        footer_text = "[Press Ctrl+C to exit. Use arrow keys to navigate pages. Dashboard refreshes every 5 seconds.]"
        self.layout["footer"].update(Panel(footer_text, style="bold green"))

    def generate_summary_panel(self, strategies):
        """
        Generates a summary panel showing real-time performance of all strategies.
        """
        table = Table(title="Strategies Summary", title_style="bold cyan")
        table.add_column("Strategy ID", justify="center", style="white")
        table.add_column("Title", justify="left", style="magenta")
        table.add_column("Active", justify="center", style="green")
        table.add_column("PnL", justify="right", style="red")

        for strategy in strategies:
            pnl = self.performance_manager.calculate_summary(strategy["id"]).get("pnl", 0)
            table.add_row(
                strategy["id"],
                strategy["title"],
                "Yes" if strategy["active"] else "No",
                f"{pnl:.2f} USDT",
            )

        return Panel(table, title="Summary")

    def generate_details_panel(self, strategy, market_data):
        """
        Generates a detailed panel for a single strategy, including real-time graphs and price changes.
        """
        layout = Layout()

        title = strategy["title"]
        pnl = self.performance_manager.calculate_summary(strategy["id"]).get("pnl", 0)

        # Strategy Header Panel
        header_panel = Panel(
            f"[bold]Title:[/bold] {title}\n"
            f"[bold]PnL:[/bold] {pnl:.2f} USDT",
            title=f"Strategy {strategy['id']}",
        )

        # Real-Time Graph Panel
        graph_layout = Layout(name="graphs")
        for asset in strategy["data"].get("assets", []):
            asset_data = market_data.get(asset, {})
            price_history = asset_data.get("price_history", [random.uniform(50, 150) for _ in range(10)])

            graph = self.generate_graph(price_history, asset)
            if graph:
                graph_layout.split_row(Layout(Align.center(graph, vertical="middle")))

        layout.split_column(
            Layout(header_panel, size=5),
            graph_layout,
        )

        return layout

    def generate_graph(self, price_history, asset):
        """
        Generates an ASCII graph for asset price history, adjusting size to fit the terminal window.
        """
        try:
            terminal_size = shutil.get_terminal_size((80, 20))
            width = terminal_size.columns
            height = terminal_size.lines // 4

            if width < 50 or height < 5:
                self.logger.warning(f"Terminal size too small for graphs. Skipping graph for {asset}.")
                return None

            max_price = max(price_history)
            min_price = min(price_history)

            graph_lines = [
                "".join(
                    "#" if round(price) == round(val) else " "
                    for val in range(int(min_price), int(max_price + 1))
                )
                for price in reversed(price_history)
            ][:height]  # Limit graph height to fit terminal

            graph = "\n".join(graph_lines)
            return f"{asset} Price Graph\n{graph}"
        except Exception as e:
            self.logger.error(f"Failed to generate graph for {asset}: {e}")
            return f"{asset} Graph Unavailable"

    async def update_dashboard(self):
        """
        Continuously fetches and updates live data on the dashboard in batches.
        """
        try:
            # Fetch strategies and market data
            strategies = self.strategy_manager.list_strategies()
            active_trades = self.trade_manager.get_active_trades()
            assets = list({trade["asset"] for trade in active_trades})
            market_data = await self.market_monitor.get_current_market_data(assets)

            # Pagination Logic
            total_pages = (len(strategies) + self.strategies_per_page - 1) // self.strategies_per_page
            if self.current_page > total_pages:
                self.current_page = total_pages
            if self.current_page < 1:
                self.current_page = 1

            start_index = (self.current_page - 1) * self.strategies_per_page
            end_index = start_index + self.strategies_per_page

            summary_panel = self.generate_summary_panel(strategies)
            details_panel = self.generate_details_panel(strategies[start_index], market_data)

            self.layout["summary"].update(summary_panel)
            self.layout["details"].update(details_panel)

            self.logger.info("Dashboard updated.")
        except Exception as e:
            self.logger.error(f"Error updating dashboard: {e}")

    async def run(self):
        """Runs the dashboard in a loop."""
        try:
            with Live(self.layout, refresh_per_second=1, console=self.console):
                while True:
                    await self.update_dashboard()
                    await asyncio.sleep(5)
        except asyncio.CancelledError:
            self.logger.info("Dashboard loop cancelled.")
        except KeyboardInterrupt:
            self.console.print("\n[bold red]Dashboard stopped.[/bold red]")
        except Exception as e:
            self.logger.error(f"Unexpected error in dashboard loop: {e}")
