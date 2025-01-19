import asyncio
import pandas as pd
import logging
import pandas_ta as ta
from rich.live import Live
from rich.table import Table
from cachetools import TTLCache
from typing import Dict, List, Any, Optional
from datetime import datetime
import ccxt.async_support as ccxt


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
        self.active_monitors: Dict[str, asyncio.Task] = {}
        self.cache_timestamp: Optional[datetime] = None
        self.CACHE_DURATION = 60  # seconds

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
        try:
            strategy_id = strategy['id']
            if strategy_id in self.active_monitors:
                self.logger.warning(f"Strategy {strategy_id} already being monitored")
                return

            monitor_task = asyncio.create_task(
                self.monitor_strategy(strategy)
            )
            self.active_monitors[strategy_id] = monitor_task
            self.logger.info(f"Activated monitoring for {strategy['title']}")
            
        except Exception as e:
            self.logger.error(f"Failed to activate monitoring: {e}")
            raise

    async def monitor_strategy(self, strategy):
        """
        Monitors entry and exit conditions for a strategy and executes or closes trades accordingly.
        """
        try:
            while True:
                strategy_data = await self.strategy_manager.get_strategy_data(strategy['id'])
                assets = strategy_data.get('assets', [])
                
                if not assets:
                    self.logger.warning(f"No assets for strategy {strategy['title']}")
                    return

                budget = await self.budget_manager.get_budget(strategy['id'])
                market_data = await self.get_market_data(assets)
                
                await self.check_entry_conditions(strategy, market_data, budget)
                await self.check_exit_conditions(strategy, market_data)
                await asyncio.sleep(10)  # Polling interval

        except asyncio.CancelledError:
            self.logger.info(f"Monitoring cancelled for {strategy['title']}")
        except Exception as e:
            self.logger.error(f"Error monitoring strategy: {e}")
            raise

    async def deactivate_monitoring(self, strategy_id: str):
        """
        Deactivates monitoring for a specific strategy by ID.
        """
        try:
            if strategy_id in self.active_monitors:
                self.active_monitors[strategy_id].cancel()
                del self.active_monitors[strategy_id]
                self.logger.info(f"Deactivated monitoring for {strategy_id}")
        except Exception as e:
            self.logger.error(f"Failed to deactivate monitoring: {e}")

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
        
    async def get_market_data(self, assets: List[str]) -> Dict:
        """Fetch market data with caching."""
        try:
            current_time = datetime.now()
            
            if (self.cache_timestamp and 
                (current_time - self.cache_timestamp).seconds < self.CACHE_DURATION):
                return self.market_data_cache

            market_data = {}
            for asset in assets:
                ticker = await self.exchange.fetch_ticker(asset)
                ohlcv = await self.exchange.fetch_ohlcv(asset, '1m', limit=1)
                
                market_data[asset] = {
                    'price': ticker['last'],
                    'volume': ticker['baseVolume'],
                    'high': ticker['high'],
                    'low': ticker['low'],
                    'ohlcv': ohlcv[0] if ohlcv else None
                }

            self.market_data_cache = market_data
            self.cache_timestamp = current_time
            return market_data

        except Exception as e:
            self.logger.error(f"Failed to fetch market data: {e}")
            return {}

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

    async def check_entry_conditions(self, strategy: Dict, 
                                   market_data: Dict, budget: float):
        """Check and execute entry conditions."""
        try:
            conditions = strategy.get('conditions', {}).get('entry', [])
            for condition in conditions:
                if await self._evaluate_condition(condition, market_data):
                    await self._execute_entry_trade(strategy, market_data, budget)
        except Exception as e:
            self.logger.error(f"Error checking entry conditions: {e}")

    async def check_exit_conditions(self, strategy: Dict, market_data: Dict):
        """Check and execute exit conditions."""
        try:
            conditions = strategy.get('conditions', {}).get('exit', [])
            active_trades = await self.trade_manager.get_active_trades(strategy['id'])
            
            for condition in conditions:
                if await self._evaluate_condition(condition, market_data):
                    for trade in active_trades:
                        await self._execute_exit_trade(trade, market_data)
        except Exception as e:
            self.logger.error(f"Error checking exit conditions: {e}")

    async def _evaluate_condition(self, condition: Dict, market_data: Dict) -> bool:
        """Evaluate a trading condition."""
        try:
            indicator = condition.get('indicator')
            operator = condition.get('operator')
            value = condition.get('value')
            asset = condition.get('asset')
            
            if not all([indicator, operator, value, asset]):
                return False

            current_value = await self._get_indicator_value(
                indicator, market_data[asset]
            )
            
            return self._compare_values(current_value, operator, value)
        except Exception as e:
            self.logger.error(f"Error evaluating condition: {e}")
            return False

    async def _get_indicator_value(self, indicator: str, market_data: Dict) -> float:
        """Get indicator value from market data."""
        indicators = {
            'price': lambda x: x['price'],
            'volume': lambda x: x['volume'],
            'high': lambda x: x['high'],
            'low': lambda x: x['low']
        }
        return indicators.get(indicator, lambda x: 0)(market_data)

    def _compare_values(self, current: float, operator: str, target: float) -> bool:
        """Compare values using specified operator."""
        operators = {
            '>': lambda x, y: x > y,
            '<': lambda x, y: x < y,
            '>=': lambda x, y: x >= y,
            '<=': lambda x, y: x <= y,
            '==': lambda x, y: x == y
        }
        return operators.get(operator, lambda x, y: False)(current, target)

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
