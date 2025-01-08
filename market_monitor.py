import asyncio
import pandas as pd
import logging
import pandas_ta as ta
from rich.live import Live
from rich.table import Table
from typing import Dict, List


class MarketMonitor:
    """
    Monitors active strategies, evaluates market conditions, and triggers trade executions based on strategy rules.
    Provides live updates via a dashboard and maintains WebSocket connections for real-time market data.
    """

    def __init__(self, exchange, strategy_manager, trade_manager, trade_executor, budget_manager):
        self.exchange = exchange
        self.strategy_manager = strategy_manager
        self.trade_manager = trade_manager
        self.trade_executor = trade_executor
        self.budget_manager = budget_manager
        self.logger = logging.getLogger(self.__class__.__name__)
        logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        self.dashboard_table = Table(title="Live Trading Dashboard")
        self.create_dashboard()
        self.websocket_connections = {}
        self.monitoring_active = False
        self.balance_threshold = 50  # Minimum balance threshold to trigger warnings

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
        self.dashboard_table.add_column("Budget", justify="center", style="bright_yellow", no_wrap=True)
        self.dashboard_table.add_column("Exchange Balance", justify="center", style="bright_cyan", no_wrap=True)
        self.dashboard_table.add_column("Risk Level", justify="center", style="bright_yellow", no_wrap=True)
        self.dashboard_table.add_column("Last Action", justify="center", style="bright_cyan", no_wrap=True)

    async def activate_monitoring(self, strategy):
        """
        Activates monitoring for a specific strategy.
        :param strategy: The strategy to monitor.
        """
        self.logger.info(f"Activating monitoring for strategy: {strategy['title']}")
        self.monitoring_active = True
        asyncio.create_task(self.monitor_strategy(strategy))

    async def monitor_strategy(self, strategy):
        """
        Monitors a strategy by evaluating entry conditions and triggering trades.
        :param strategy: The strategy to monitor.
        """
        strategy_name = strategy["title"]
        strategy_data = strategy["data"]

        for asset in strategy_data.get("assets", []):
            try:
                df = await self.fetch_live_data(asset)
                entry_signal = self.evaluate_conditions(strategy_data.get("conditions", {}).get("entry", []), df)

                if entry_signal:
                    self.logger.info(f"Entry signal detected for {asset}. Executing trade.")
                    await self.trade_executor.execute_trade(
                        strategy_name, asset, "buy", strategy_data
                    )
            except Exception as e:
                self.logger.error(f"Error monitoring '{strategy_name}' for asset '{asset}': {e}")

    async def deactivate_monitoring(self, strategy_id: str):
        """
        Deactivates monitoring for a specific strategy by ID.
        """
        try:
            active_trades = self.trade_manager.get_active_trades()
            trades_to_unsubscribe = [trade for trade in active_trades if trade["strategy_name"] == strategy_id]

            for trade in trades_to_unsubscribe:
                asset = trade["asset"]
                if asset in self.websocket_connections:
                    await self.exchange.websocket_unsubscribe(asset)
                    del self.websocket_connections[asset]
                    self.logger.info(f"Unsubscribed from WebSocket for {asset} (Strategy ID: {strategy_id})")

            self.logger.info(f"Monitoring deactivated for strategy ID '{strategy_id}'.")
        except Exception as e:
            self.logger.error(f"Failed to deactivate monitoring for strategy ID '{strategy_id}': {e}")

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
        Updates the dashboard with active trades, budget, and available balance.
        """
        self.dashboard_table.rows.clear()
        active_trades = self.trade_manager.get_active_trades()
        balances = await self.fetch_exchange_balances()

        for trade in active_trades:
            strategy_name = trade.get("strategy_id", "Unknown")
            asset = trade.get("asset", "Unknown")
            market_type = trade.get("market_type", "spot")
            status = trade.get("status", "Unknown")
            filled = float(trade.get("filled", 0))
            remaining = float(trade.get("remaining", 0))
            pnl = self.calculate_pnl(trade)
            budget = self.budget_manager.get_budget(strategy_name)
            balance = balances.get(asset, 0)
            risk_level = trade.get("risk_level", "Moderate")

            if balance < budget:
                self.logger.warning(f"Exchange balance for {asset} is below strategy budget.")
                self.budget_manager.update_budget(strategy_name, balance)

            balance_display = (
                f"[bold red]{balance:.2f} USDT[/bold red]"
                if balance < self.balance_threshold
                else f"{balance:.2f} USDT"
            )

            self.dashboard_table.add_row(
                strategy_name,
                asset,
                market_type,
                status,
                f"{pnl:.2f}",
                f"{(filled / (filled + remaining) * 100) if (filled + remaining) > 0 else 0:.2f}%",
                str(remaining),
                f"{budget:.2f} USDT",
                balance_display,
                risk_level,
                status,
            )
    def list_strategies(self) -> List[Dict]:
        """
        Lists all saved strategies.
        :return: A list of dictionaries with strategy details.
        """
        try:
            strategies = self.strategy_manager.list_strategies()
            return strategies
        except Exception as e:
            self.logger.error(f"Failed to list strategies: {e}")
            return []

    def evaluate_conditions(self, conditions: List[dict], df: pd.DataFrame) -> bool:
        try:
            if df.empty or len(df) < 20:
                return False

            for condition in conditions:
                indicator = condition["indicator"]
                operator = condition["operator"]
                value = condition["value"]
                params = condition.get("indicator_parameters", {})

                indicator_values = self.calculate_indicator(indicator, df, params)
                latest_value = indicator_values.iloc[-1]

                if not self.apply_operator(latest_value, operator, value):
                    return False

            return True
        except Exception as e:
            self.logger.error(f"Error evaluating conditions: {e}")
            return False
    
    
    async def fetch_live_data(self, asset: str) -> pd.DataFrame:
        """
        Fetches live market data via WebSocket or REST API fallback.
        :param asset: The trading pair (e.g., 'BTC/USDT').
        :return: DataFrame with OHLCV market data.
        """
        try:
            # Attempt WebSocket connection if available
            if asset in self.websocket_connections:
                data = await self.websocket_connections[asset].fetch_live_data()
            else:
                # Fallback to REST API if WebSocket isn't active
                ohlcv = await self.exchange.fetch_ohlcv(asset, timeframe="1m", limit=500)

                # Transform data into DataFrame
                df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
                df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
                df.set_index("datetime", inplace=True)
                return df

        except Exception as e:
            self.logger.error(f"Error fetching live data for {asset}: {e}")
            return pd.DataFrame()  # Return empty DataFrame on error

        
    async def fetch_exchange_balances(self) -> dict:
        """
        Fetches available balances for all assets from the exchange.
        :return: Dictionary with asset symbols and available balances.
        """
        try:
            balances = await self.exchange.fetch_balance()
            return {symbol: balance['free'] for symbol, balance in balances['total'].items()}
        except Exception as e:
            self.logger.error(f"Failed to fetch balances: {e}")
            return {}
        
    async def get_current_market_data(self, asset: str) -> pd.DataFrame:
        try:
            tickers = await self.exchange.fetch_tickers()
            data = tickers.get(asset, {})
            if not data:
                self.logger.warning(f"No market data returned for {asset}.")
                return pd.DataFrame()

            # Convert to DataFrame
            df = pd.DataFrame([data], columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("datetime", inplace=True)
            return df
        except Exception as e:
            self.logger.error(f"Failed to fetch market data for {asset}: {e}")
            return pd.DataFrame()


        except Exception as e:
            self.logger.error(f"Error fetching current market data for {asset}: {e}")
            return pd.DataFrame()  # Return empty DataFrame on failure