import asyncio
import pandas as pd
import logging
from rich.live import Live
from rich.table import Table
from typing import Dict, List


class MarketMonitor:
    """
    Monitors active strategies, evaluates market conditions, and triggers trade executions based on strategy rules.
    Provides live updates via a dashboard and maintains WebSocket connections for real-time market data.
    """

    def __init__(self, exchange, strategy_manager, trade_manager, trade_executor):
        self.exchange = exchange
        self.strategy_manager = strategy_manager
        self.trade_manager = trade_manager
        self.trade_executor = trade_executor
        self.logger = logging.getLogger(self.__class__.__name__)
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        self.dashboard_table = Table(title="Live Trading Dashboard")
        self.create_dashboard()
        self.websocket_connections = {}
        self.monitoring_active = False  # Tracks whether monitoring is active

    def create_dashboard(self):
        """
        Initializes the live dashboard structure.
        """
        self.dashboard_table.add_column("Strategy Name", justify="center", style="cyan", no_wrap=True)
        self.dashboard_table.add_column("Asset", justify="center", style="magenta", no_wrap=True)
        self.dashboard_table.add_column("Market Type", justify="center", style="blue", no_wrap=True)
        self.dashboard_table.add_column("Trade Status", justify="center", style="green", no_wrap=True)
        self.dashboard_table.add_column("PnL", justify="center", style="red", no_wrap=True)
        self.dashboard_table.add_column("Filled (%)", justify="center", style="yellow", no_wrap=True)
        self.dashboard_table.add_column("Remaining", justify="center", style="white", no_wrap=True)
        self.dashboard_table.add_column("Risk Level", justify="center", style="bright_yellow", no_wrap=True)
        self.dashboard_table.add_column("Last Action", justify="center", style="bright_cyan", no_wrap=True)

    async def activate_monitoring(self, strategy):
        """
        Activates monitoring for a specific strategy.
        :param strategy: The strategy to monitor.
        """
        self.logger.info(f"Activating monitoring for strategy: {strategy['title']}")
        self.monitoring_active = True

        # Monitor the strategy in a separate coroutine
        asyncio.create_task(self.monitor_strategy(strategy))

    async def deactivate_monitoring(self):
        """
        Deactivates all monitoring.
        """
        self.logger.info("Deactivating all monitoring.")
        self.monitoring_active = False
        self.websocket_connections.clear()

    async def start_monitoring(self):
        """
        Main loop for monitoring active strategies and updating the dashboard.
        """
        await self.exchange.load_markets()
        self.logger.info("MarketMonitor: Starting monitoring loop...")
        with Live(self.dashboard_table, refresh_per_second=1) as live_dashboard:
            while self.monitoring_active:
                try:
                    await self.update_dashboard()
                except Exception as e:
                    self.logger.error(f"MarketMonitor: Error in monitoring loop - {e}")
                await asyncio.sleep(5)

    async def update_dashboard(self):
        """
        Updates the dashboard with active trades and their statuses.
        """
        self.dashboard_table.rows.clear()  # Clear the table for fresh data

        # Get active strategies and trades
        active_strategies = self.strategy_manager.list_strategies()
        active_trades = self.trade_manager.get_active_trades()

        # Update WebSocket subscriptions for relevant assets
        await self.update_websocket_subscriptions(active_trades)

        # Map strategies and trades to dashboard rows
        for trade in active_trades:
            strategy_name = trade.get("strategy_id", "Unknown")
            asset = trade.get("asset", "Unknown")
            market_type = trade.get("market_type", "spot")
            status = trade.get("status", "Unknown")
            filled = float(trade.get("filled", 0))
            remaining = float(trade.get("remaining", 0))
            pnl = self.calculate_pnl(trade)
            risk_level = trade.get("risk_level", "Moderate")
            last_action = status if status in ["open", "closed"] else "Pending"

            self.dashboard_table.add_row(
                strategy_name,
                asset,
                market_type,
                status,
                f"{pnl:.2f}",
                f"{(filled / (filled + remaining) * 100) if (filled + remaining) > 0 else 0:.2f}%",
                str(remaining),
                risk_level,
                last_action,
            )

    async def update_websocket_subscriptions(self, trades: List[Dict]):
        """
        Updates WebSocket subscriptions to ensure real-time market data for active trades.
        """
        subscribed_assets = set(self.websocket_connections.keys())
        required_assets = {trade["asset"] for trade in trades}

        # Unsubscribe from assets no longer needed
        for asset in subscribed_assets - required_assets:
            if self.websocket_connections.get(asset):
                await self.exchange.websocket_unsubscribe(asset)
                del self.websocket_connections[asset]
                self.logger.info(f"Unsubscribed from WebSocket for asset: {asset}")

        # Subscribe to new assets
        for asset in required_assets - subscribed_assets:
            try:
                connection = await self.exchange.websocket_subscribe(asset)
                self.websocket_connections[asset] = connection
                self.logger.info(f"Subscribed to WebSocket for asset: {asset}")
            except Exception as e:
                self.logger.error(f"Failed to subscribe to WebSocket for asset {asset}: {e}")

    async def monitor_strategy(self, strategy):
        """
        Monitors and evaluates a specific strategy across its assets.
        """
        strategy_name = strategy["title"]
        strategy_data = strategy["data"]

        for asset in strategy_data["assets"]:
            try:
                df = await self.fetch_live_data(asset)  # Ensure this is awaited only if async
                if df.empty:
                    self.logger.warning(f"No data available for asset '{asset}'. Skipping.")
                    continue

                entry_signal = self.evaluate_conditions(strategy_data["conditions"]["entry"], df)
                exit_signal = self.evaluate_conditions(strategy_data["conditions"]["exit"], df)

                if entry_signal:
                    await self.trade_executor.execute_trade(strategy_name, asset, "buy", strategy_data)
                elif exit_signal:
                    await self.trade_executor.execute_trade(strategy_name, asset, "sell", strategy_data)
            except Exception as e:
                self.logger.error(f"MarketMonitor: Error monitoring '{strategy_name}' for asset '{asset}' - {e}")

    async def fetch_live_data(self, asset: str) -> pd.DataFrame:
        """
        Fetches live market data via WebSocket or falls back to REST API.
        """
        if asset in self.websocket_connections:
            try:
                # Example: Fetch data from an active WebSocket connection
                data = await self.websocket_connections[asset].fetch_live_data()
                return pd.DataFrame(data)
            except Exception as e:
                self.logger.warning(f"WebSocket data for {asset} unavailable, falling back to REST API: {e}")

        try:
            # Fallback to REST API for OHLCV data
            ohlcv = await self.exchange.fetch_ohlcv(asset, timeframe="1m", limit=500)
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("datetime", inplace=True)
            return df
        except Exception as e:
            self.logger.error(f"Error fetching live data for {asset}: {e}")
            return pd.DataFrame()  # Return an empty dataframe if fetching fails

    def calculate_pnl(self, trade: Dict) -> float:
        """
        Calculates profit and loss for a trade.
        """
        try:
            entry_price = float(trade.get("entry_price", 0))
            exit_price = float(trade.get("average", 0))
            amount = float(trade.get("filled", 0))

            if trade["status"] == "closed":
                pnl = (exit_price - entry_price) * amount if trade["side"] == "buy" else (entry_price - exit_price) * amount
                return pnl
        except Exception as e:
            self.logger.error(f"MarketMonitor: Error calculating PnL for trade {trade['trade_id']} - {e}")
        return 0.0

    def evaluate_conditions(self, conditions: List[Dict], df: pd.DataFrame) -> bool:
        """
        Evaluates conditions for a strategy and determines if they are met.
        """
        for condition in conditions:
            indicator = condition.get("indicator")
            operator = condition.get("operator")
            value = condition.get("value")

            if indicator not in df.columns:
                self.logger.error(f"Indicator '{indicator}' not found in data frame.")
                return False

            last_value = df[indicator].iloc[-1]
            if not self.compare(last_value, operator, value):
                return False
        return True

    def compare(self, a: float, operator: str, b: float) -> bool:
        """
        Compares two values with the given operator.
        """
        operators = {
            ">": lambda x, y: x > y,
            "<": lambda x, y: x < y,
            ">=": lambda x, y: x >= y,
            "<=": lambda x, y: x <= y,
            "==": lambda x, y: x == y,
        }
        return operators[operator](a, b)
