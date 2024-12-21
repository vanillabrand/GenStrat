import asyncio
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn
import random

class Dashboard:
    """
    Live Dashboard displaying strategies, trades, and market data.
    """

    def __init__(self):
        self.console = Console()
        self.live_table = Table(title="📊 Live Trading Dashboard", title_style="bold cyan", box="SIMPLE")
        self.progress_bars = {}
        self.progress = Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=None),
            TextColumn("[progress.percentage]{task.percentage:>3.1f}%"),
            console=self.console,
        )
        self.setup_table()

    def setup_table(self):
        """
        Sets up the structure of the live dashboard table.
        """
        self.live_table.add_column("Strategy", justify="left", style="bold green")
        self.live_table.add_column("Pair", justify="center", style="bold yellow")
        self.live_table.add_column("Type", justify="center", style="bold magenta")
        self.live_table.add_column("Status", justify="center", style="cyan")
        self.live_table.add_column("PnL (%)", justify="right", style="bold red")
        self.live_table.add_column("Leverage", justify="center", style="bold white")
        self.live_table.add_column("Last Update", justify="right", style="dim")

    def add_progress_bar(self, task_name):
        """
        Adds a progress bar for a new task to track strategy progress.
        """
        if task_name not in self.progress_bars:
            self.progress_bars[task_name] = self.progress.add_task(task_name, total=100)

    def update_progress_bar(self, task_name, progress_value):
        """
        Updates the progress bar for a specific task.
        """
        if task_name in self.progress_bars:
            self.progress.update(self.progress_bars[task_name], completed=progress_value)

    async def update_table(self, strategies):
        """
        Updates the dashboard table with live data from active strategies.
        """
        self.live_table.rows.clear()  # Clear the table before updating

        for strategy in strategies:
            pair = strategy.get("pair", "Unknown")
            strategy_name = strategy.get("name", "N/A")
            pnl = f"{strategy.get('pnl', 0.0):.2f}%"
            leverage = strategy.get("leverage", "1x")
            status = strategy.get("status", "Active")
            last_update = strategy.get("last_update", "Just Now")

            self.live_table.add_row(
                strategy_name,
                pair,
                strategy.get("type", "Spot"),
                Text(status, style="green" if "Active" in status else "red"),
                pnl,
                leverage,
                last_update,
            )

    async def display_dashboard(self, fetch_strategy_data):
        """
        Displays the live dashboard with real-time updates.
        :param fetch_strategy_data: A coroutine function that fetches live strategy data.
        """
        with Live(
            Panel(self.live_table, title="🚀 Trading Insights", title_align="left"),
            refresh_per_second=2,
            console=self.console,
        ):
            with self.progress:
                while True:
                    strategies = await fetch_strategy_data()
                    await self.update_table(strategies)
                    for strategy in strategies:
                        task_name = strategy["name"]
                        progress = strategy.get("progress", random.randint(10, 90))
                        self.add_progress_bar(task_name)
                        self.update_progress_bar(task_name, progress)
                    await asyncio.sleep(1)

# Example Usage
async def mock_fetch_strategy_data():
    """
    Mock function to simulate fetching strategy data.
    """
    return [
        {
            "name": "Strategy 1",
            "pair": "BTC/USDT",
            "type": "Futures",
            "status": "Active",
            "pnl": random.uniform(-10, 15),
            "leverage": "5x",
            "last_update": "2 seconds ago",
            "progress": random.randint(0, 100),
        },
        {
            "name": "Strategy 2",
            "pair": "ETH/USDT",
            "type": "Spot",
            "status": "Inactive",
            "pnl": random.uniform(-5, 20),
            "leverage": "1x",
            "last_update": "10 seconds ago",
            "progress": random.randint(0, 100),
        },
    ]

async def main():
    dashboard = Dashboard()
    await dashboard.display_dashboard(mock_fetch_strategy_data)

if __name__ == "__main__":
    asyncio.run(main())
