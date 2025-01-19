import logging
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.progress import Progress
import time
from typing import Dict, List, Any
from datetime import datetime
import asyncio
import random
import shutil


class Dashboard:
    """
    Dashboard for displaying live updates on trades, strategies, and market details.
    Includes real-time graphs and price changes for assets in each strategy.
    """

    def __init__(self, strategy_manager, trade_manager, performance_manager):
        self.console = Console()
        self.logger = logging.getLogger(__name__)
        self.strategy_manager = strategy_manager
        self.trade_manager = trade_manager
        self.performance_manager = performance_manager
        self.current_page = 0
        self.strategies_per_page = 1
        self.live_update = None

    async def start(self):
        """Initialize live dashboard"""
        layout = self._create_layout()
        with Live(layout, refresh_per_second=1) as live:
            self.live_update = live
            while True:
                try:
                    await self._update_dashboard(layout)
                    await asyncio.sleep(1)
                except KeyboardInterrupt:
                    break

    def _create_layout(self) -> Layout:
        """Create dashboard layout"""
        layout = Layout(name="root")
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )
        layout["main"].split_row(
            Layout(name="strategy_info"),
            Layout(name="trades")
        )
        layout["strategy_info"].split_column(
            Layout(name="overview"),
            Layout(name="performance"),
            Layout(name="risk")
        )
        return layout

    async def _update_dashboard(self, layout: Layout):
        """Update dashboard components"""
        strategies = self.strategy_manager.list_strategies()
        current_strategy = strategies[self.current_page]
        
        # Update strategy overview
        layout["header"].update(
            Panel(f"Strategy Dashboard - {current_strategy['title']} "
                  f"({self.current_page + 1}/{len(strategies)})")
        )

        # Strategy Overview
        overview = self._create_strategy_overview(current_strategy)
        layout["overview"].update(Panel(overview, title="Strategy Overview"))

        # Active Trades
        trades_table = self._create_trades_table(current_strategy['id'])
        layout["trades"].update(Panel(trades_table, title="Active Trades"))

        # Performance Metrics
        performance = self._create_performance_panel(current_strategy['id'])
        layout["performance"].update(Panel(performance, title="Performance Metrics"))

        # Risk Analytics
        risk = self._create_risk_panel(current_strategy['id'])
        layout["risk"].update(Panel(risk, title="Risk Analytics"))

        # Controls
        controls = self._create_controls()
        layout["footer"].update(controls)

    def _create_strategy_overview(self, strategy: Dict) -> Table:
        """Create strategy overview table"""
        table = Table(show_header=False)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Status", "🟢 Active" if strategy['active'] else "🔴 Inactive")
        table.add_row("Market Type", strategy['market_type'])
        table.add_row("Assets", ", ".join(strategy['assets']))
        table.add_row("Created", strategy['created_at'])
        table.add_row("Last Updated", strategy['updated_at'])
        
        return table

    def _create_trades_table(self, strategy_id: str) -> Table:
        """Create active trades table"""
        table = Table()
        table.add_column("ID", style="cyan")
        table.add_column("Asset", style="green")
        table.add_column("Type", style="magenta")
        table.add_column("Entry", style="yellow")
        table.add_column("Current", style="yellow")
        table.add_column("P&L", style="red" if float < 0 else "green")
        table.add_column("Status", style="blue")
        
        trades = self.trade_manager.get_strategy_trades(strategy_id)
        for trade in trades:
            pnl = self._calculate_pnl(trade)
            table.add_row(
                trade['id'][:8],
                trade['asset'],
                trade['type'],
                f"${trade['entry_price']:.2f}",
                f"${trade['current_price']:.2f}",
                f"{pnl:.2f}%",
                trade['status']
            )
        
        return table

    def _create_performance_panel(self, strategy_id: str) -> Table:
        """Create performance metrics panel"""
        metrics = self.performance_manager.get_metrics(strategy_id)
        table = Table(show_header=False)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Total P&L", f"${metrics['total_pnl']:.2f}")
        table.add_row("Win Rate", f"{metrics['win_rate']:.1f}%")
        table.add_row("Avg Trade", f"${metrics['avg_trade']:.2f}")
        table.add_row("Sharpe Ratio", f"{metrics['sharpe_ratio']:.2f}")
        table.add_row("Max Drawdown", f"{metrics['max_drawdown']:.1f}%")
        
        return table

    def _create_risk_panel(self, strategy_id: str) -> Table:
        """Create risk analytics panel"""
        risk_metrics = self.performance_manager.get_risk_metrics(strategy_id)
        table = Table(show_header=False)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Open Risk", f"${risk_metrics['open_risk']:.2f}")
        table.add_row("Used Margin", f"${risk_metrics['used_margin']:.2f}")
        table.add_row("Free Margin", f"${risk_metrics['free_margin']:.2f}")
        table.add_row("Margin Level", f"{risk_metrics['margin_level']:.1f}%")
        
        return table

    def _create_controls(self) -> Panel:
        """Create control panel"""
        controls = [
            "[cyan]←/→[/cyan] Navigate Strategies",
            "[cyan]Space[/cyan] Toggle Strategy",
            "[cyan]C[/cyan] Close All Trades",
            "[cyan]Q[/cyan] Quit"
        ]
        return Panel(" | ".join(controls), title="Controls")

    async def handle_input(self, key: str):
        """Handle user input"""
        if key == "right":
            self.current_page = (self.current_page + 1) % len(self.strategy_manager.list_strategies())
        elif key == "left":
            self.current_page = (self.current_page - 1) % len(self.strategy_manager.list_strategies())
        elif key == "space":
            strategy = self.strategy_manager.list_strategies()[self.current_page]
            await self.strategy_manager.toggle_strategy(strategy['id'])
        elif key == "c":
            strategy = self.strategy_manager.list_strategies()[self.current_page]
            await self.trade_manager.close_all_strategy_trades(strategy['id'])

    def _calculate_pnl(self, trade: Dict) -> float:
        """Calculate trade P&L percentage"""
        if trade['type'] == 'long':
            return ((trade['current_price'] - trade['entry_price']) / trade['entry_price']) * 100
        else:
            return ((trade['entry_price'] - trade['current_price']) / trade['entry_price']) * 100
