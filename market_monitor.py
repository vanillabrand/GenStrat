import asyncio
import pandas as pd
import logging
import pandas_ta as ta
from rich.live import Live
from rich.table import Table
from cachetools import TTLCache
from typing import Dict, List


class MarketMonitor:
    """
    Monitors active strategies, evaluates market conditions, and triggers trade executions based on strategy rules.
    Provides live updates via a dashboard and maintains WebSocket connections for real-time market data.
    """

    def __init__(self, exchange, strategy_manager, trade_manager, trade_executor, budget_manager, trade_suggestion_manager):
        self.exchange = exchange
        self.strategy_manager = strategy_manager
        self.trade_manager = trade_manager
        self.trade_executor = trade_executor
        self.budget_manager = budget_manager
        self.trade_suggestion_manager = trade_suggestion_manager
        self.logger = logging.getLogger(self.__class__.__name__)
        logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        self.dashboard_table = Table(title="Live Trading Dashboard")
        self.create_dashboard()
        self.websocket_connections = {}
        self.monitoring_active = False
        self.balance_threshold = 50  # Minimum balance threshold to trigger warnings
        self.market_data_cache = TTLCache(maxsize=100, ttl=10)  # Cache with 10-second TTL

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
        Monitors entry and exit conditions for a strategy and executes or closes trades accordingly.
        """
        try:
            strategy_data = self.strategy_manager.get_strategy_data(strategy["id"])
            assets = strategy_data.get("assets", [])
            if not assets:
                self.logger.warning(f"Strategy '{strategy['title']}' has no assets defined.")
                return

            # Fetch the total budget for the strategy
            budget = self.budget_manager.get_budget(strategy["id"])

            # Fetch market data
            market_data = await self.get_current_market_data(assets)

            # Generate trades with budget allocation
            suggested_trades = self.trade_suggestion_manager.generate_trades(strategy_data, market_data, budget)

            # Check if trades have budget allocations
            all_trades_have_budget = all("budget_allocation" in trade for trade in suggested_trades)
            if not all_trades_have_budget:
                self.logger.warning(f"TradeSuggestionManager did not return budget allocations for some trades. Falling back to dynamic allocation.")

                # Allocate budget dynamically across assets
                asset_weights = {asset: 1 for asset in assets}  # Equal weighting for simplicity
                self.budget_manager.allocate_budget_dynamically(budget, asset_weights)

                # Assign budget allocation to trades manually
                for trade in suggested_trades:
                    asset = trade["asset"]
                    trade["budget_allocation"] = self.budget_manager.get_budget(asset)
                    self.logger.info(f"Allocated {trade['budget_allocation']:.2f} USDT to trade for asset '{asset}'.")

            # Process each trade
            for trade_details in suggested_trades:
                allocated_budget = trade_details.get("budget_allocation", 0)

                # Validate and execute trades
                if self.trade_executor.validate_and_execute_trade(strategy["title"], trade_details):
                    # Deduct the allocated budget
                    if self.budget_manager.update_budget(strategy["id"], allocated_budget):
                        self.logger.info(f"Trade executed for {trade_details['asset']} under strategy '{strategy['title']}'. Budget allocated: {allocated_budget:.2f} USDT.")
                else:
                    # Return unused budget if trade execution fails
                    self.budget_manager.return_budget(strategy["id"], allocated_budget)
        except Exception as e:
            self.logger.error(f"Error monitoring strategy '{strategy['title']}': {e}")

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
            self.update_dashboard_row(trade, balances)

    def update_dashboard_row(self, trade, balances):
        """
        Updates a single row in the dashboard for a trade.
        """
        asset = trade.get("asset", "Unknown")
        balance = balances.get(asset, 0)
        balance_warning = balance < self.balance_threshold

        balance_display = (
            f"[bold red]{balance:.2f} USDT[/bold red]" if balance_warning else f"{balance:.2f} USDT"
        )

        pnl = self.calculate_pnl(trade)
        budget = self.budget_manager.get_budget(trade["strategy_id"])  # Fetch the remaining budget
        risk_level = trade.get("risk_level", "Moderate")
        self.dashboard_table.add_row(
            trade["strategy_id"], asset, trade["market_type"],
            trade["status"], f"{pnl:.2f}", "N/A", "N/A",
            f"{budget:.2f} USDT", balance_display, risk_level,
            trade.get("last_action", "N/A")
        )
        
    async def get_current_market_data(self, assets):
        """
        Fetches current market data for multiple assets in a batch request.
        """
        uncached_assets = [asset for asset in assets if asset not in self.market_data_cache]
        if uncached_assets:
            try:
                market_data = await self.exchange.fetch_tickers(uncached_assets)
                for symbol, data in market_data.items():
                    self.market_data_cache[symbol] = {
                        "price": data["last"],
                        "high": data["high"],
                        "low": data["low"],
                        "volume": data["baseVolume"],
                        "change_24h": data.get("percentage", 0),
                    }
            except Exception as e:
                self.logger.error(f"Error fetching market data: {e}")

        return {asset: self.market_data_cache.get(asset, {}) for asset in assets}

    async def fetch_exchange_balances(self) -> dict:
        """
        Fetches available balances for all assets from the exchange.
        """
        try:
            balances = await self.exchange.fetch_balance()
            return {symbol: balance['free'] for symbol, balance in balances['total'].items()}
        except Exception as e:
            self.logger.error(f"Failed to fetch balances: {e}")
            return {}

    def evaluate_conditions(self, conditions: List[dict], asset_data: dict) -> bool:
        """
        Evaluates entry or exit conditions for an asset based on market data.
        """
        try:
            for condition in conditions:
                indicator = condition["indicator"]
                operator = condition["operator"]
                value = condition["value"]

                if indicator not in asset_data:
                    self.logger.warning(f"Missing indicator {indicator} in market data.")
                    return False

                current_value = asset_data[indicator]
                if not self.apply_operator(current_value, operator, value):
                    return False

            return True
        except Exception as e:
            self.logger.error(f"Error evaluating conditions: {e}")
            return False

    def calculate_pnl(self, trade):
        """
        Calculates profit and loss (PnL) for a trade.
        """
        try:
            entry_price = float(trade.get("entry_price", 0))
            current_price = float(trade.get("current_price", 0))
            size = float(trade.get("size", 0))
            return (current_price - entry_price) * size
        except Exception as e:
            self.logger.error(f"Error calculating PnL for trade: {e}")
            return 0.0

    def apply_operator(self, value, operator, target):
        """
        Applies a comparison operator to a value and a target.
        """
        operators = {
            ">": lambda x, y: x > y,
            "<": lambda x, y: x < y,
            ">=": lambda x, y: x >= y,
            "<=": lambda x, y: x <= y,
            "==": lambda x, y: x == y,
        }
        return operators.get(operator, lambda x, y: False)(value, target)

    def calculate_indicator(self, indicator, df, params):
        """
        Calculates the specified indicator for the given DataFrame.
        """
        try:
            if hasattr(ta, indicator):
                return getattr(ta, indicator)(df["close"], **params)
            else:
                self.logger.warning(f"Indicator {indicator} is not recognized by pandas_ta.")
                return pd.Series(dtype="float64")
        except Exception as e:
            self.logger.error(f"Error calculating indicator {indicator}: {e}")
            return pd.Series(dtype="float64")
