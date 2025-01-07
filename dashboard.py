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

    def __init__(self, exchange, strategy_manager, trade_manager, market_monitor, performance_manager=None):
        self.console = Console()
        self.exchange = exchange
        self.strategy_manager = strategy_manager
        self.trade_manager = trade_manager
        self.market_monitor = market_monitor
        self.performance_manager = performance_manager
        self.logger = logging.getLogger(self.__class__.__name__)

        # Initialize the layout
        self.layout = Layout()
        self.layout.split(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )
        self.layout["body"].split_row(
            Layout(name="strategies"),
            Layout(name="trades"),
            Layout(name="market"),
        )
        self.init_header()
        self.init_footer()

    def init_header(self):
        """Initializes the header layout."""
        header_text = Text("GenStrat Trading Dashboard", style="bold cyan")
        self.layout["header"].update(Panel(header_text, title="Welcome", title_align="left"))

    def init_footer(self):
        """Initializes the footer layout."""
        footer_text = "[Press Ctrl+C to exit. Dashboard refreshes every 5 seconds.]"
        self.layout["footer"].update(Panel(footer_text, style="bold green"))

    def generate_market_panel(self):
        """Generates a panel displaying live market information."""
        table = Table(title="Market Overview", style="blue")
        table.add_column("Asset", justify="center", style="magenta")
        table.add_column("Price", justify="right", style="white")
        table.add_column("24h Change", justify="right", style="green")
        table.add_column("Volume", justify="right", style="cyan")

        try:
            market_data = self.market_monitor.get_current_market_data()
            if not market_data:
                self.logger.warning("No market data available.")
                table.add_row("N/A", "N/A", "N/A", "N/A")
            else:
                for asset, data in market_data.items():
                    table.add_row(
                        asset,
                        f"{data['price']:.2f}" if data.get('price') else "N/A",
                        f"{data['change']:.2f}%" if data.get('change') else "N/A",
                        f"{data['volume']:,}" if data.get('volume') else "N/A",
                    )
        except Exception as e:
            self.logger.error(f"Failed to fetch market data: {e}")
            table.add_row("N/A", "N/A", "N/A", "N/A")

        return Panel(table, title="Market Overview")

    def generate_trades_panel(self):
        """Generates a panel displaying live trade details."""
        table = Table(title="Active Trades", style="yellow")
        table.add_column("Trade ID", justify="center", style="white")
        table.add_column("Strategy", justify="center", style="magenta")
        table.add_column("Asset", justify="center", style="cyan")
        table.add_column("Side", justify="center", style="green")
        table.add_column("Status", justify="center", style="blue")
        table.add_column("PnL", justify="right", style="red")

        try:
            trades = self.trade_manager.get_active_trades()
            if not trades:
                self.logger.warning("No active trades available.")
                table.add_row("N/A", "N/A", "N/A", "N/A", "N/A", "N/A")
            else:
                for trade in trades:
                    table.add_row(
                        trade['trade_id'],
                        trade['strategy_name'],
                        trade['asset'],
                        trade['side'],
                        trade['status'],
                        f"{trade.get('pnl', 0):.2f} USDT"
                    )
        except Exception as e:
            self.logger.error(f"Failed to fetch trade data: {e}")
            table.add_row("N/A", "N/A", "N/A", "N/A", "N/A", "N/A")

        return Panel(table, title="Active Trades")

    def generate_strategies_panel(self):
        """Generates a panel displaying active strategies and their details."""
        table = Table(title="Active Strategies", style="cyan")
        table.add_column("Strategy ID", justify="center", style="white")
        table.add_column("Title", justify="left", style="magenta")
        table.add_column("Active", justify="center", style="green")
        table.add_column("Assets", justify="left", style="cyan")

        try:
            strategies = self.strategy_manager.list_strategies()
            if not strategies:
                self.logger.warning("No active strategies available.")
                table.add_row("N/A", "N/A", "N/A", "N/A")
            else:
                for strategy in strategies:
                    table.add_row(
                        strategy['id'],
                        strategy['title'],
                        "Yes" if strategy['active'] else "No",
                        ", ".join(strategy['data'].get('assets', [])),
                    )
        except Exception as e:
            self.logger.error(f"Failed to fetch strategies: {e}")
            table.add_row("N/A", "N/A", "N/A", "N/A")

        return Panel(table, title="Active Strategies")

    async def update_dashboard(self):
        """Continuously fetches and updates live data on the dashboard."""
        with Live(self.layout, refresh_per_second=1, console=self.console):
            while True:
                try:
                    strategies_panel = self.generate_strategies_panel()
                    trades_panel = self.generate_trades_panel()
                    market_panel = self.generate_market_panel()

                    # Safely update panels
                    if strategies_panel:
                        self.layout["body"]["strategies"].update(strategies_panel)
                    if trades_panel:
                        self.layout["body"]["trades"].update(trades_panel)
                    if market_panel:
                        self.layout["body"]["market"].update(market_panel)
                except Exception as e:
                    self.logger.error(f"Dashboard update error: {e}")
                await asyncio.sleep(5)  # Refresh every 5 seconds

    async def run(self):
        """Runs the dashboard in a loop."""
        try:
            await self.update_dashboard()
        except asyncio.CancelledError:
            self.logger.info("Dashboard loop cancelled.")
        except KeyboardInterrupt:
            self.console.print("\n[bold red]Dashboard stopped.[/bold red]")
        except Exception as e:
            self.logger.error(f"Unexpected error in dashboard loop: {e}")
