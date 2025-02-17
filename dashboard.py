import logging
import asyncio
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from datetime import datetime, timezone
from typing import Dict, List, Any
import random
import shutil
from aioconsole import ainput  # Ensure you have installed via: pip install aioconsole

class Dashboard:
    """
    Dashboard for displaying live updates on strategies, trades, performance metrics,
    and live streaming asset details.
    
    - Displays all trades (not just active ones).
    - Uses websocket-based ticker updates for asset details when available.
    - Provides asynchronous keyboard controls.
    """

    def __init__(self, strategy_manager, trade_manager, performance_manager, exchange):
        self.console = Console()
        self.logger = logging.getLogger(__name__)
        self.strategy_manager = strategy_manager
        self.trade_manager = trade_manager
        self.performance_manager = performance_manager
        self.exchange = exchange  # This exchange instance should support websockets (ccxt.pro)
        self.current_page = 0
        self.strategies_per_page = 1
        self.live_update = None
        self._listening = True  # Control flag for key listening

    async def start(self):
        """Start the live dashboard and concurrently listen for keyboard input."""
        layout = self._create_layout()
        key_listener_task = asyncio.create_task(self._listen_for_keys())
        with Live(layout, refresh_per_second=1, console=self.console) as live:
            self.live_update = live
            while True:
                try:
                    await self._update_dashboard(layout)
                    await asyncio.sleep(1)
                except KeyboardInterrupt:
                    self.logger.info("Dashboard update loop interrupted by user.")
                    self._listening = False  # Stop key listener loop
                    break
                except Exception as e:
                    self.logger.error(f"Dashboard update error: {e}", exc_info=True)
                    await asyncio.sleep(1)
        key_listener_task.cancel()

    def _create_layout(self) -> Layout:
        """
        Creates a layout with:
          - Header: Title and strategy info.
          - Main area: Divided into two rows.
              • Upper row: Two columns (strategy info and trades table).
              • Lower row: Asset details panel (live ticker updates).
          - Footer: Control instructions.
        """
        layout = Layout(name="root")
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )
        # Main area: split into upper and asset details panels
        layout["main"].split_column(
            Layout(name="upper"),
            Layout(name="asset_details",minimum_size=10)  # Adjust height as needed
        )
        # Upper row: two columns (strategy_info and trades)
        layout["upper"].split_row(
            Layout(name="strategy_info"),
            Layout(name="trades")
        )
        # Within strategy_info, further split into overview, performance, and risk panels.
        layout["strategy_info"].split_column(
            Layout(name="overview"),
            Layout(name="performance"),
            Layout(name="risk")
        )
        return layout

    async def _update_dashboard(self, layout: Layout):
        """Fetch and update all panels with the latest data."""
        strategies = await self.strategy_manager.list_strategies()
        if not strategies:
            layout["header"].update(Panel("No strategies found.", style="red"))
            layout["overview"].update(Panel("No data available."))
            layout["trades"].update(Panel("No trades available."))
            layout["performance"].update(Panel("No performance data available."))
            layout["risk"].update(Panel("No risk metrics available."))
            layout["asset_details"].update(Panel("No asset data available."))
            layout["footer"].update(Panel("Press Ctrl+C to exit."))
            return

        # Ensure current_page is within valid range.
        if self.current_page >= len(strategies):
            self.current_page = max(0, len(strategies) - 1)
        current_strategy = strategies[self.current_page]

        # Header: strategy title and page count.
        header_text = (
            f"Strategy Dashboard - {current_strategy.get('title', 'N/A')} "
            f"({self.current_page + 1}/{len(strategies)})"
        )
        layout["header"].update(Panel(header_text, style="bold cyan"))

        # Strategy Overview
        overview = self._create_strategy_overview(current_strategy)
        layout["overview"].update(Panel(overview, title="Strategy Overview"))

        # Trades Table (showing all trades)
        trades_table = self._create_trades_table(current_strategy.get("id"))
        layout["trades"].update(Panel(trades_table, title="All Trades"))

        # Performance Metrics
        performance = self._create_performance_panel(current_strategy.get("id"))
        layout["performance"].update(Panel(performance, title="Performance Metrics"))

        # Risk Analytics
        risk = self._create_risk_panel(current_strategy.get("id"))
        layout["risk"].update(Panel(risk, title="Risk Analytics"))

        # Asset Details Panel with live ticker updates.
        asset_panel = await self._create_asset_details_panel(current_strategy)
        layout["asset_details"].update(asset_panel)

        # Footer Controls
        controls = self._create_controls()
        layout["footer"].update(controls)

    def _create_strategy_overview(self, strategy: Dict) -> Table:
        """Builds a table summarizing the current strategy's overview."""
        table = Table(show_header=False)
        table.add_column("Metric", style="cyan", no_wrap=False)
        table.add_column("Value", style="green", no_wrap=False)
        status = "🟢 Active" if strategy.get("active", False) else "🔴 Inactive"
        table.add_row("Status", status)
        table.add_row("Market Type", str(strategy.get("market_type", "N/A")))
        assets = strategy.get("assets", [])
        table.add_row("Assets", ", ".join(assets) if assets else "None")
        table.add_row("Rationale", strategy.get("rationale", "N/A"))
        return table

    def _create_trades_table(self, strategy_id: str) -> Table:
        """
        Builds a table listing all trades for the strategy.
        This version does not filter out inactive or cancelled trades—it displays all.
        """
        table = Table(title="Trades")
        table.add_column("ID", style="cyan", no_wrap=False)
        table.add_column("Asset", style="green", no_wrap=False)
        table.add_column("Type", style="magenta", no_wrap=False)
        table.add_column("Entry", style="yellow", no_wrap=False)
        table.add_column("Current", style="yellow", no_wrap=False)
        table.add_column("P&L", justify="right", no_wrap=False)
        table.add_column("Status", style="blue", no_wrap=False)
        
        # Retrieve all trades for this strategy.
        trades = self.trade_manager.get_strategy_trades(strategy_id)
        for trade in trades:
            try:
                # Convert entry and current prices to float; default entry to zero if missing.
                entry_price = float(trade.get("entry_price", 0.0))
                current_price = float(trade.get("current_price", entry_price))
                
                # Calculate profit or loss.
                pnl = self._calculate_pnl(trade)
                color = "green" if pnl >= 0 else "red"
                
                # Get the trade ID and truncate it for display.
                trade_id = str(trade.get("id", ""))[:8]
                
                # Add the row to the table.
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
        """Builds a table showing performance metrics for the strategy."""
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
        """Builds a table showing risk metrics for the strategy."""
        risk_metrics = self.performance_manager.get_risk_metrics(strategy_id)
        table = Table(show_header=False)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Open Risk", f"${risk_metrics.get('open_risk', 0.0):.2f}")
        table.add_row("Used Margin", f"${risk_metrics.get('used_margin', 0.0):.2f}")
        table.add_row("Free Margin", f"${risk_metrics.get('free_margin', 0.0):.2f}")
        table.add_row("Margin Level", f"{risk_metrics.get('margin_level', 0.0):.1f}%")
        return table

    async def _create_asset_details_panel(self, strategy: Dict) -> Panel:
        """
        Creates a panel displaying live ticker details for each asset in the strategy.
        Uses websocket-based updates (via exchange.watch_ticker) when available;
        otherwise, falls back to using exchange.fetch_ticker.
        """
        assets = strategy.get("assets", [])
        if not assets:
            return Panel("No assets available.", title="Asset Details")
        
        tasks = []
        for asset in assets:
            if hasattr(self.exchange, "watch_ticker") and asyncio.iscoroutinefunction(self.exchange.watch_ticker):
                tasks.append(self.exchange.watch_ticker(asset))
            else:
                loop = asyncio.get_event_loop()
                tasks.append(loop.run_in_executor(None, self.exchange.fetch_ticker, asset))
        tickers = await asyncio.gather(*tasks, return_exceptions=True)
        table = Table(title="Asset Details")
        table.add_column("Asset", style="cyan")
        table.add_column("Last Price", style="green")
        table.add_column("Volume", style="yellow")
        for asset, ticker in zip(assets, tickers):
            if isinstance(ticker, Exception):
                table.add_row(asset, "Error", "Error")
            else:
                last = ticker.get("last", "N/A")
                vol = ticker.get("volume", "N/A")
                table.add_row(asset, str(last), str(vol))
        return Panel(table, title="Asset Details")

    def _create_controls(self) -> Panel:
        """Creates a control panel displaying available keyboard commands."""
        controls = [
            "[cyan]←/→[/cyan] Navigate Strategies",
            "[cyan]Space[/cyan] Toggle Strategy",
            "[cyan]C[/cyan] Close All Trades",
            "[cyan]Q[/cyan] Quit"
        ]
        return Panel(" | ".join(controls), title="Controls", style="bold")

    async def _listen_for_keys(self):
        """
        Asynchronous key listener.
        Continuously reads user input (non-blocking via aioconsole) and dispatches to handle_input.
        """
        while self._listening:
            try:
                key = (await ainput("Key Command (←, →, Space, C, Q): ")).strip()
                if key:
                    await self.handle_input(key)
            except Exception as e:
                self.logger.error(f"Key listener error: {e}", exc_info=True)
                await asyncio.sleep(0.5)

    async def handle_input(self, key: str):
        """
        Handles key input commands.
        Valid keys:
          - "right" or "→": Next strategy.
          - "left" or "←": Previous strategy.
          - "space": Toggle the active state of the current strategy.
          - "c": Close all trades for the current strategy.
          - "q": Quit the dashboard.
        """
        strategies = await self.strategy_manager.list_strategies()
        if not strategies:
            return
        if key.lower() in ("right", "→", ".", ">"):
            self.current_page = (self.current_page + 1) % len(strategies)
        elif key.lower() in ("left", "←", ",", "<"):
            self.current_page = (self.current_page - 1) % len(strategies)
        elif key.lower() == "space":
            strategy = strategies[self.current_page]
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

    async def pre_validate_and_fetch_prices(self, strategy_id: str) -> Dict:
        """
        Loads a strategy and fetches market data (tickers) for each asset.
        """
        try:
            strategy = await self.strategy_manager.load_strategy(strategy_id)
            assets = strategy.get("data", {}).get("assets", [])
            if not assets:
                raise ValueError("Strategy has no defined assets.")
            market_data = {}
            for asset in assets:
                if asyncio.iscoroutinefunction(self.exchange.fetch_ticker):
                    ticker = await self.exchange.fetch_ticker(asset)
                else:
                    ticker = self.exchange.fetch_ticker(asset)
                market_data[asset] = ticker
            if not market_data:
                raise ValueError("Failed to fetch market data for any asset.")
            return {"strategy": strategy, "market_data": market_data}
        except Exception as e:
            self.logger.error(f"Pre-validation failed: {e}", exc_info=True)
            raise
