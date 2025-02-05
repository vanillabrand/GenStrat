import logging
import asyncio
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from datetime import datetime
from typing import Dict, List, Any
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
        with Live(layout, refresh_per_second=1, console=self.console) as live:
            self.live_update = live
            while True:
                try:
                    await self._update_dashboard(layout)
                    await asyncio.sleep(1)
                except KeyboardInterrupt:
                    self.logger.info("Dashboard update loop interrupted by user.")
                    break
                except Exception as e:
                    self.logger.error(f"Dashboard update error: {e}", exc_info=True)
                    await asyncio.sleep(1)

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
        strategies = await self.strategy_manager.list_strategies()
        if not strategies:
            layout["header"].update(Panel("No strategies found.", style="red"))
            layout["overview"].update(Panel("No data available."))
            layout["trades"].update(Panel("No trades available."))
            layout["performance"].update(Panel("No performance data available."))
            layout["risk"].update(Panel("No risk metrics available."))
            layout["footer"].update(Panel("Press Ctrl+C to exit."))
            return

        # Ensure current_page is within valid range
        if self.current_page >= len(strategies):
            self.current_page = max(0, len(strategies) - 1)

        current_strategy = strategies[self.current_page]

        # Use safe .get() for key accesses in header update
        header_text = (
            f"Strategy Dashboard - {current_strategy.get('title', 'N/A')} "
            f"({self.current_page + 1}/{len(strategies)})"
        )
        layout["header"].update(Panel(header_text, style="bold cyan"))

        # Update strategy overview panel using safe key access
        overview = self._create_strategy_overview(current_strategy)
        layout["overview"].update(Panel(overview, title="Strategy Overview"))

        # Update active trades panel
        trades_table = self._create_trades_table(current_strategy.get("id"))
        layout["trades"].update(Panel(trades_table, title="Active Trades"))

        # Update performance metrics panel
        performance = self._create_performance_panel(current_strategy.get("id"))
        layout["performance"].update(Panel(performance, title="Performance Metrics"))

        # Update risk analytics panel
        risk = self._create_risk_panel(current_strategy.get("id"))
        layout["risk"].update(Panel(risk, title="Risk Analytics"))

        # Update footer controls
        controls = self._create_controls()
        layout["footer"].update(controls)

    def _create_strategy_overview(self, strategy: Dict) -> Table:
        """Create strategy overview table with safe key access."""
        table = Table(show_header=False)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        status = "🟢 Active" if strategy.get("active", False) else "🔴 Inactive"
        table.add_row("Status", status)
        table.add_row("Market Type", str(strategy.get("market_type", "N/A")))
        assets = strategy.get("assets", [])
        table.add_row("Assets", ", ".join(assets) if assets else "None")
        table.add_row("Created", strategy.get("created_at", "N/A"))
        table.add_row("Last Updated", strategy.get("updated_at", "N/A"))
        return table

    def _create_trades_table(self, strategy_id: str) -> Table:
        """Create active trades table with safe access."""
        table = Table()
        table.add_column("ID", style="cyan")
        table.add_column("Asset", style="green")
        table.add_column("Type", style="magenta")
        table.add_column("Entry", style="yellow")
        table.add_column("Current", style="yellow")
        table.add_column("P&L", justify="right")
        table.add_column("Status", style="blue")
        
        trades = self.trade_manager.get_strategy_trades(strategy_id)
        for trade in trades:
            try:
                entry_price = float(trade.get("entry_price", 0.0))
                current_price = float(trade.get("current_price", entry_price))
                pnl = self._calculate_pnl(trade)
                color = "green" if pnl >= 0 else "red"
                trade_id = str(trade.get("id", ""))[:8]
                table.add_row(
                    trade_id,
                    trade.get("asset", "N/A"),
                    trade.get("type", "N/A"),
                    f"${entry_price:.2f}",
                    f"${current_price:.2f}",
                    f"[{color}]{pnl:.2f}%[/{color}]",
                    trade.get("status", "N/A")
                )
            except Exception as e:
                self.logger.error(f"Error processing trade {trade.get('id')}: {e}", exc_info=True)
        return table

    def _create_performance_panel(self, strategy_id: str) -> Table:
        """Create performance metrics panel using safe access."""
        # Assuming performance_manager.calculate_summary() returns a dictionary
        metrics = self.performance_manager.calculate_summary(strategy_id)
        table = Table(show_header=False)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Total P&L", f"${metrics.get('total_profit', 0.0):.2f}")
        table.add_row("Win Rate", f"{metrics.get('success_rate', 0.0):.1f}%")
        table.add_row("Total Trades", str(metrics.get("total_trades", 0)))
        table.add_row("Max Drawdown", f"{metrics.get('max_drawdown', 0.0):.1f}%")
        return table

    def _create_risk_panel(self, strategy_id: str) -> Table:
        """Create risk analytics panel using safe access."""
        risk_metrics = self.performance_manager.get_risk_metrics(strategy_id)
        table = Table(show_header=False)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Open Risk", f"${risk_metrics.get('open_risk', 0.0):.2f}")
        table.add_row("Used Margin", f"${risk_metrics.get('used_margin', 0.0):.2f}")
        table.add_row("Free Margin", f"${risk_metrics.get('free_margin', 0.0):.2f}")
        table.add_row("Margin Level", f"{risk_metrics.get('margin_level', 0.0):.1f}%")
        return table

    def _create_controls(self) -> Panel:
        """Create control panel for user guidance."""
        controls = [
            "[cyan]←/→[/cyan] Navigate Strategies",
            "[cyan]Space[/cyan] Toggle Strategy",
            "[cyan]C[/cyan] Close All Trades",
            "[cyan]Q[/cyan] Quit"
        ]
        return Panel(" | ".join(controls), title="Controls", style="bold")

    async def handle_input(self, key: str):
        """
        (Optional) Handle user input commands asynchronously.
        """
        strategies = await self.strategy_manager.list_strategies()
        if not strategies:
            return
        if key.lower() == "right":
            self.current_page = (self.current_page + 1) % len(strategies)
        elif key.lower() == "left":
            self.current_page = (self.current_page - 1) % len(strategies)
        elif key.lower() == "space":
            strategy = strategies[self.current_page]
            # Example toggle functionality (ensure toggle_strategy exists)
            await self.strategy_manager.toggle_strategy(strategy.get("id"))
        elif key.lower() == "c":
            strategy = strategies[self.current_page]
            await self.trade_manager.close_all_strategy_trades(strategy.get("id"))
        elif key.lower() == "q":
            raise KeyboardInterrupt()

    def _calculate_pnl(self, trade: Dict) -> float:
        """Calculates the percentage profit/loss for a trade."""
        try:
            entry_price = float(trade.get("entry_price", 0))
            current_price = float(trade.get("current_price", entry_price))
            trade_type = trade.get("type", "long")
            if entry_price == 0:
                return 0.0
            if trade_type.lower() == "long":
                return ((current_price - entry_price) / entry_price) * 100
            else:
                return ((entry_price - current_price) / entry_price) * 100
        except Exception as e:
            self.logger.error(f"Failed to calculate PnL for trade {trade.get('id')}: {e}", exc_info=True)
            return 0.0

    async def validate_strategy(self, strategy_id: str):
        """
        Validates a strategy by fetching necessary market data.
        """
        try:
            enriched_data = await self.pre_validate_and_fetch_prices(strategy_id)
            return enriched_data
        except Exception as e:
            self.logger.error(f"Strategy validation failed: {e}", exc_info=True)
            raise
