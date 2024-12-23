from rich.console import Console
from rich.table import Table
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
import asyncio
import logging

class Dashboard:
    """
    Dashboard for displaying live updates on trades, strategies, and market details.
    """

    def __init__(self, exchange, strategy_manager, performance_manager):
        self.console = Console()
        self.exchange = exchange
        self.strategy_manager = strategy_manager
        self.performance_manager = performance_manager
        self.logger = logging.getLogger(self.__class__.__name__)

        # Dashboard layout
        self.layout = Layout()
        self.layout.split(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )
        self.layout["body"].split_row(
            Layout(name="strategies"),
            Layout(name="trades"),
            Layout(name="market")
        )
        self.init_header()
        self.init_footer()

    def init_header(self):
        """Initializes the header layout."""
        header_text = Text("GenStrat Trading Dashboard", style="bold cyan")
        self.layout["header"].update(Panel(header_text, title="Welcome", title_align="left"))

    def init_footer(self):
        """Initializes the footer layout."""
        footer_text = "[Press Ctrl+C to exit. Use arrow keys to navigate when applicable.]"
        self.layout["footer"].update(Panel(footer_text, style="bold green"))

    def generate_strategies_panel(self):
        """Generates a panel displaying strategies."""
        table = Table(title="Active Strategies", style="cyan")
        table.add_column("ID", justify="center", style="white")
        table.add_column("Title", justify="left", style="magenta")
        table.add_column("Active", justify="center", style="green")

        strategies = self.strategy_manager.list_strategies()
        for strategy in strategies:
            table.add_row(
                strategy['id'],
                strategy['title'],
                "Yes" if strategy['active'] else "No"
            )

        return Panel(table, title="Strategies")

    def generate_trades_panel(self):
        """Generates a panel displaying active trades."""
        table = Table(title="Live Trades", style="yellow")
        table.add_column("Trade ID", justify="center", style="white")
        table.add_column("Asset", justify="center", style="magenta")
        table.add_column("Status", justify="center", style="green")
        table.add_column("PnL", justify="right", style="red")

        trades = self.strategy_manager.get_active_trades()
        for trade in trades:
            table.add_row(
                trade['trade_id'],
                trade['asset'],
                trade['status'],
                f"{trade.get('pnl', 0):.2f} USDT"
            )

        return Panel(table, title="Trades")

    def generate_market_panel(self):
        """Generates a panel displaying market information."""
        table = Table(title="Market Overview", style="blue")
        table.add_column("Asset", justify="center", style="magenta")
        table.add_column("Price", justify="right", style="white")
        table.add_column("24h Change", justify="right", style="green")

        try:
            market_data = asyncio.run(self.exchange.fetch_tickers())
            for asset, data in market_data.items():
                table.add_row(
                    asset,
                    f"{data['last']:.2f}",
                    f"{data['percentage']:.2f}%"
                )
        except Exception as e:
            self.logger.error(f"Failed to fetch market data: {e}")
            table.add_row("N/A", "N/A", "N/A")

        return Panel(table, title="Market")

    async def update_dashboard(self):
        """Updates the dashboard with live data."""
        with Live(self.layout, refresh_per_second=2, console=self.console):
            while True:
                try:
                    self.layout["body"]["strategies"].update(self.generate_strategies_panel())
                    self.layout["body"]["trades"].update(self.generate_trades_panel())
                    self.layout["body"]["market"].update(self.generate_market_panel())
                except Exception as e:
                    self.logger.error(f"Dashboard update error: {e}")

                await asyncio.sleep(5)

    def run(self):
        """Runs the dashboard in a loop."""
        try:
            asyncio.run(self.update_dashboard())
        except KeyboardInterrupt:
            self.console.print("\n[bold red]Dashboard stopped.[/bold red]")
