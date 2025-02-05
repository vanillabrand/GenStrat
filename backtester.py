import logging
import random
import json
from typing import Dict, List, Any, Optional, Type
from functools import lru_cache
from multiprocessing import Pool
from datetime import datetime
import asyncio

import pandas as pd
import numpy as np

import backtrader as bt
from backtrader.feeds import PandasData

import asciichartpy
from rich.console import Console
from rich.table import Table

# Import your custom managers
from trade_suggestion_manager import TradeSuggestionManager
from strategy_manager import StrategyManager
from budget_manager import BudgetManager
from risk_manager import RiskManager

# ---------------- Module-Level Helper ----------------
def validate_trade_helper(trade: Dict[str, Any], strategy_data: Dict[str, Any]) -> bool:
    """
    Validates a trade based on strategy rules.
    This helper is defined at the module level so that it is picklable for multiprocessing.
    Returns True if the trade contains required fields; otherwise, False.
    """
    try:
        # For our purposes, we require that the trade dict contains a "price" and "stop_loss".
        if trade.get("price") is None or trade.get("stop_loss") is None:
            raise ValueError("Missing required fields: price or stop_loss.")
        return True
    except Exception as e:
        import sys
        print(f"Trade validation failed for trade {trade.get('id', '?')}: {e}", file=sys.stderr)
        return False

# ---------------- Backtester Class ----------------
class Backtester:
    """
    Handles the execution of backtests, scenario testing, and synthetic data generation.
    Integrates with a ccxt-based exchange (e.g., Bitget) for historical OHLCV retrieval,
    plus StrategyManager, BudgetManager, RiskManager, and TradeSuggestionManager for
    validating and producing realistic trade flows via Backtrader.
    """

    def __init__(
        self,
        strategy_manager: StrategyManager,
        budget_manager: BudgetManager,
        risk_manager: RiskManager,
        trade_suggestion_manager: TradeSuggestionManager,
        exchange: Any  # ccxt or ccxt.async_support instance
    ):
        self.strategy_manager = strategy_manager
        self.budget_manager = budget_manager
        self.risk_manager = risk_manager
        self.trade_suggestion_manager = trade_suggestion_manager
        self.logger = logging.getLogger(self.__class__.__name__)
        self.console = Console()
        self.exchange = exchange

    # --- Data Validation & Conversion ---
    def _validate_and_convert_data(self, historical_data: pd.DataFrame) -> PandasData:
        """
        Validates and converts historical data into a Backtrader-compatible feed.
        Ensures required columns and sets 'timestamp' as a DateTimeIndex.
        """
        required_columns = {"timestamp", "open", "high", "low", "close", "volume"}
        missing_cols = required_columns - set(historical_data.columns)
        if missing_cols:
            raise ValueError(f"Missing required columns in DataFrame: {missing_cols}")
        historical_data['timestamp'] = pd.to_datetime(historical_data['timestamp'])
        historical_data.set_index('timestamp', inplace=True)
        return bt.feeds.PandasData(dataname=historical_data)

    @lru_cache(maxsize=10)
    async def _load_strategy(self, strategy_id: str) -> Dict[str, Any]:
        """
        Loads strategy data asynchronously from StrategyManager.
        Cached for faster repeated usage.
        """
        try:
            strategy = await self.strategy_manager.load_strategy(strategy_id)
            if not strategy:
                raise ValueError(f"Strategy {strategy_id} not found.")
            return strategy
        except Exception as e:
            self.logger.error(f"Failed to load strategy: {e}", exc_info=True)
            raise

    # --- Synthetic Data Generation ---
    async def generate_synthetic_data(
        self,
        scenario: str = "sideways",
        timeframe: str = "1m",
        duration_days: int = 1
    ) -> pd.DataFrame:
        """
        Generates synthetic market data asynchronously for scenario-based testing.
        'scenario' can be 'bull', 'bear', 'sideways', or a custom string.
        """
        try:
            frequency_map = {"1m": "min", "5m": "5min", "10m": "10min", "1h": "h", "1d": "D", "1w": "W"}
            freq = frequency_map.get(timeframe, "min")
            if timeframe.endswith("m"):
                minutes_per_candle = int(timeframe[:-1])
                num_points = (duration_days * 24 * 60) // minutes_per_candle
            elif timeframe.endswith("h"):
                hours_per_candle = int(timeframe[:-1])
                num_points = (duration_days * 24) // hours_per_candle
            elif timeframe.endswith("d"):
                num_points = duration_days
            elif timeframe.endswith("w"):
                num_points = duration_days // 7
            else:
                num_points = (duration_days * 24 * 60)
            timestamps = pd.date_range(start="2023-01-01", periods=num_points, freq=freq)
            base_price = 100.0
            prices = []
            volumes = []
            for _ in range(num_points):
                if scenario == "bull":
                    base_price += random.uniform(0.1, 1)
                elif scenario == "bear":
                    base_price -= random.uniform(0.1, 1)
                elif scenario == "sideways":
                    base_price += random.uniform(-0.5, 0.5)
                else:
                    base_price += random.uniform(-1.0, 1.0)
                base_price = max(base_price, 1)
                prices.append(base_price)
                volumes.append(random.randint(100, 1000))
            data = pd.DataFrame({
                "timestamp": timestamps,
                "open": prices[:-1] + [prices[-1]],
                "high": [p + random.uniform(0, 0.5) for p in prices],
                "low": [p - random.uniform(0, 0.5) for p in prices],
                "close": prices,
                "volume": volumes,
            })
            self.logger.info(f"Synthetic data generated for scenario: {scenario}, timeframe: {timeframe}, days: {duration_days}")
            return data
        except Exception as e:
            self.logger.error(f"Error generating synthetic data: {e}", exc_info=True)
            raise

    def _simulate_market_data(self, historical_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Simulates a snapshot of market data from the last historical data point.
        """
        latest_data = historical_data.iloc[-1].to_dict()
        return {
            "current_price": latest_data["close"],
            "high": latest_data["high"],
            "low": latest_data["low"],
            "volume": latest_data["volume"],
        }

    # --- Exchange (ccxt) Historical Data Fetching ---
    async def fetch_exchange_data(
        self,
        asset: str,
        timeframe: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Fetches OHLCV data from a ccxt-based exchange for a given asset within the specified date range.
        Timestamps are in milliseconds.
        """
        try:
            start_ts = int(pd.Timestamp(start_date).timestamp() * 1000)
            end_ts = int(pd.Timestamp(end_date).timestamp() * 1000)
            all_ohlcv = []
            current_ts = start_ts
            limit = 500
            while True:
                if asyncio.iscoroutinefunction(self.exchange.fetch_ohlcv):
                    ohlcv = await self.exchange.fetch_ohlcv(asset, timeframe=timeframe, since=current_ts, limit=limit)
                else:
                    ohlcv = self.exchange.fetch_ohlcv(asset, timeframe=timeframe, since=current_ts, limit=limit)
                if not ohlcv:
                    break
                filtered = [row for row in ohlcv if row[0] <= end_ts]
                all_ohlcv.extend(filtered)
                if len(ohlcv) < limit or not filtered:
                    break
                last_ts = ohlcv[-1][0]
                if last_ts >= end_ts:
                    break
                current_ts = last_ts + 1
            if not all_ohlcv:
                self.logger.warning(f"No OHLCV data fetched for {asset} in the given range.")
                return pd.DataFrame()
            data = pd.DataFrame(all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            data["timestamp"] = pd.to_datetime(data["timestamp"], unit="ms")
            return data
        except Exception as e:
            self.logger.error(f"Error fetching OHLCV for {asset}: {e}", exc_info=True)
            return pd.DataFrame()

    async def _fetch_exchange_ohlcv_for_assets(
        self,
        assets: List[str],
        timeframe: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Fetches and combines OHLCV data for multiple assets from the exchange.
        """
        try:
            frames = []
            for asset in assets:
                self.logger.info(f"Fetching data for {asset}...")
                df = await self.fetch_exchange_data(asset, timeframe, start_date, end_date)
                if not df.empty:
                    df["asset"] = asset
                    frames.append(df)
                else:
                    self.logger.warning(f"No data returned for {asset}.")
            if frames:
                combined = pd.concat(frames, ignore_index=True)
                self.logger.info(f"Combined data for assets: {assets}")
                return combined
            else:
                return pd.DataFrame()
        except Exception as e:
            self.logger.error(f"Error fetching exchange OHLCV for assets: {e}", exc_info=True)
            return pd.DataFrame()

    # --- Trade Validation Logic ---
    def _validate_trades_parallel(
        self,
        trades: List[Dict[str, Any]],
        strategy_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Validates trades in parallel using a process pool for CPU-bound checks.
        Uses the module-level helper 'validate_trade_helper' to ensure picklability.
        """
        try:
            with Pool(processes=4) as pool:
                results = pool.starmap(validate_trade_helper, [(trade, strategy_data) for trade in trades])
            return [trade for trade, valid in zip(trades, results) if valid]
        except Exception as e:
            self.logger.error(f"Parallel trade validation failed: {e}", exc_info=True)
            return []

    # --- Cerebro Initialization & Execution ---
    def _initialize_cerebro(self, historical_data: pd.DataFrame, starting_cash: float) -> bt.Cerebro:
        """
        Initializes the Backtrader Cerebro engine with the provided historical data and starting cash.
        """
        if not isinstance(historical_data, pd.DataFrame):
            raise ValueError("Historical data must be a pandas DataFrame")
        if not isinstance(starting_cash, (int, float)) or starting_cash <= 0:
            raise ValueError("Starting cash must be a positive number")
        try:
            cerebro = bt.Cerebro()
            data_feed = self._validate_and_convert_data(historical_data)
            cerebro.adddata(data_feed)
            cerebro.broker.set_cash(starting_cash)
            return cerebro
        except Exception as e:
            self.logger.error(f"Failed to initialize Cerebro: {e}", exc_info=True)
            raise

    # --- Dynamic Strategy Creation with Advanced Risk Management ---
    def _create_bt_strategy(self, strategy_data: Dict[str, Any], trades: List[Dict[str, Any]]) -> Type[bt.Strategy]:
        """
        Dynamically creates a Backtrader Strategy class based on the provided strategy data and validated trades.
        This implementation dynamically creates indicator instances for all conditions and implements advanced risk management
        using both fixed risk parameters and ATR-based dynamic trailing stop.
        """
        # Use the Backtrader indicators module dynamically
        import backtrader.indicators as btind

        class DynamicStrategy(bt.Strategy):
            params = strategy_data.get("trade_parameters", {})

            def __init__(self):
                # Prepare entry and exit conditions lists
                self.entry_conditions = []
                self.exit_conditions = []
                conditions = strategy_data.get("conditions", {})
                entry_conditions_data = conditions.get("entry", [])
                exit_conditions_data = conditions.get("exit", [])

                # Dynamically create indicator instances for each condition
                for cond in entry_conditions_data:
                    ind_name = cond.get("indicator")
                    operator = cond.get("operator")
                    threshold = cond.get("value")
                    ind_params = cond.get("indicator_parameters", {})
                    # Dynamically load any indicator from btind
                    ind_class = getattr(btind, ind_name, None)
                    if ind_class is None:
                        self.log(f"Indicator '{ind_name}' not found in backtrader.indicators.", logging.ERROR)
                        continue
                    instance = ind_class(self.data.close, **ind_params)
                    self.entry_conditions.append((instance, operator, threshold))

                for cond in exit_conditions_data:
                    ind_name = cond.get("indicator")
                    operator = cond.get("operator")
                    threshold = cond.get("value")
                    ind_params = cond.get("indicator_parameters", {})
                    ind_class = getattr(btind, ind_name, None)
                    if ind_class is None:
                        self.log(f"Indicator '{ind_name}' not found in backtrader.indicators.", logging.ERROR)
                        continue
                    instance = ind_class(self.data.close, **ind_params)
                    self.exit_conditions.append((instance, operator, threshold))

                # Advanced Risk Management: fixed and ATR-based
                risk_params = strategy_data.get("risk_management", {})
                self.fixed_stop_loss_pct = risk_params.get("stop_loss", None)
                self.fixed_take_profit_pct = risk_params.get("take_profit", None)
                # ATR-based trailing stop parameters
                self.atr_period = risk_params.get("atr_period", 14)
                self.atr_multiplier = risk_params.get("atr_multiplier", 3)
                self.atr = bt.indicators.ATR(self.data, period=self.atr_period)
                self.trailing_stop = None

                self.order = None
                self.buy_price = None

            def next(self):
                # If there's an open order, wait until it is executed
                if self.order:
                    return

                if not self.position:
                    # Evaluate all entry conditions
                    if all(self._evaluate_condition(ind, op, thr) for (ind, op, thr) in self.entry_conditions):
                        self.order = self.buy()
                        self.buy_price = self.data.close[0]
                        # Set initial trailing stop
                        self.trailing_stop = self.data.close[0] - self.atr[0] * self.atr_multiplier
                else:
                    # Update the trailing stop if price is favorable
                    new_trailing = self.data.close[0] - self.atr[0] * self.atr_multiplier
                    if new_trailing > self.trailing_stop:
                        self.trailing_stop = new_trailing

                    # Evaluate exit conditions
                    exit_signal = all(self._evaluate_condition(ind, op, thr) for (ind, op, thr) in self.exit_conditions)
                    current_price = self.data.close[0]
                    risk_exit = False
                    # Fixed risk parameters
                    if self.fixed_stop_loss_pct is not None:
                        if current_price <= self.buy_price * (1 - self.fixed_stop_loss_pct):
                            risk_exit = True
                    if self.fixed_take_profit_pct is not None:
                        if current_price >= self.buy_price * (1 + self.fixed_take_profit_pct):
                            risk_exit = True

                    # Exit if any exit condition is met, if risk management is triggered, or if price falls below trailing stop
                    if exit_signal or risk_exit or (self.trailing_stop is not None and current_price < self.trailing_stop):
                        self.order = self.close()

            def _evaluate_condition(self, indicator, operator, threshold) -> bool:
                """
                Evaluates a condition based on the current indicator value, operator, and threshold.
                """
                current_value = indicator[0]
                try:
                    if operator == "<":
                        return current_value < threshold
                    elif operator == ">":
                        return current_value > threshold
                    elif operator == "==":
                        return current_value == threshold
                    elif operator == "<=":
                        return current_value <= threshold
                    elif operator == ">=":
                        return current_value >= threshold
                    else:
                        return False
                except Exception as e:
                    self.log(f"Error evaluating condition: {e}", logging.ERROR)
                    return False

            def log(self, txt, dt=None):
                dt = dt or self.datas[0].datetime.date(0)
                print(f"{dt.isoformat()} {txt}")

        return DynamicStrategy

    # --- Running a Backtest ---
    async def run_backtest(self, strategy_id: str, historical_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Runs a backtest:
         1. Loads the strategy.
         2. Retrieves the budget and generates AI-based trade suggestions.
         3. Validates trades in parallel.
         4. Initializes Cerebro and runs the backtest.
         5. Processes and returns performance metrics.
        """
        if not strategy_id or historical_data.empty:
            raise ValueError("Invalid strategy_id or empty historical data.")
        try:
            strategy = await self._load_strategy(strategy_id)
            strategy_data = strategy["data"]
            self.logger.info(f"Loaded strategy '{strategy.get('title', 'N/A')}' for backtest.")

            budget = await self.budget_manager.get_budget(strategy_id)
            starting_cash = float(budget or 100000.0)

            trade_suggestions = await self.trade_suggestion_manager.generate_trades(
                strategy_id, strategy_data, {}, starting_cash
            )
            valid_trades = self._validate_trades_parallel(trade_suggestions, strategy_data)
            if not valid_trades:
                raise ValueError("No valid trades generated for backtest.")

            cerebro = self._initialize_cerebro(historical_data, starting_cash)
            strategy_class = self._create_bt_strategy(strategy_data, valid_trades)
            cerebro.addstrategy(strategy_class)

            cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharperatio")
            cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
            cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
            cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")

            results = cerebro.run()
            if not results:
                raise ValueError("Backtest produced no results.")
            return self._process_results(results[0])
        except Exception as e:
            self.logger.error(f"Backtest failed for strategy_id='{strategy_id}': {e}", exc_info=True)
            raise

    # --- Pre-Validation & Price Fetching ---
    async def pre_validate_and_fetch_prices(self, strategy_id: str) -> Dict:
        """
        Loads a strategy and fetches market data (e.g., tickers) for each asset.
        """
        try:
            strategy = await self._load_strategy(strategy_id)
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

    # --- Result Processing ---
    def _process_results(self, results) -> Dict[str, Any]:
        """
        Processes analyzer results from Cerebro and returns a summary dictionary.
        """
        try:
            returns = results.analyzers.returns.get_analysis()
            sharpe = results.analyzers.sharperatio.get_analysis()
            drawdown = results.analyzers.drawdown.get_analysis()
            trades = results.analyzers.trades.get_analysis()
            stats = {
                'initial_value': returns.get('starting', 0.0),
                'final_value': returns.get('end', 0.0),
                'return': ((returns.get('end', 0.0) / returns.get('starting', 1.0)) - 1) * 100,
                'sharpe_ratio': sharpe.get('sharperatio', 0.0),
                'max_drawdown': drawdown.get('max', {}).get('drawdown', 0.0),
                'total_trades': trades.get('total', {}).get('total', 0),
                'won_trades': trades.get('won', {}).get('total', 0),
                'lost_trades': trades.get('lost', {}).get('total', 0)
            }
            stats['win_rate'] = (stats['won_trades'] / stats['total_trades'] * 100) if stats['total_trades'] > 0 else 0.0
            self.logger.info(f"Backtest results: {stats}")
            return stats
        except Exception as e:
            self.logger.error(f"Error processing backtest results: {e}", exc_info=True)
            return {
                'initial_value': 0.0,
                'final_value': 0.0,
                'return': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0,
                'total_trades': 0,
                'won_trades': 0,
                'lost_trades': 0,
                'win_rate': 0.0
            }

    # --- Optional Summaries & ASCII Plotting ---
    def _generate_summary_table(self, initial_value: float, final_value: float, results: List[Any]):
        """
        Generates a Rich table summarizing backtest results.
        """
        table = Table(title="Backtest Summary")
        table.add_column("Metric", justify="left")
        table.add_column("Value", justify="right")
        table.add_row("Starting Portfolio Value", f"{initial_value:.2f} USDT")
        table.add_row("Ending Portfolio Value", f"{final_value:.2f} USDT")
        table.add_row("Net Profit/Loss", f"{final_value - initial_value:.2f} USDT")
        self.console.print(table)

    def _plot_ascii_results(self, historical_data: pd.DataFrame):
        """
        Visualizes backtest results using ASCII charts.
        """
        try:
            closes = historical_data['close'].dropna().tolist()
            if not closes:
                raise ValueError("No close prices available for ASCII plotting.")
            for i in range(1, len(closes) + 1):
                ascii_chart = asciichartpy.plot(closes[:i], {"height": 20, "format": "{:>8.2f}"})
                self.console.clear()
                self.console.print(ascii_chart)
        except Exception as e:
            self.logger.error(f"Failed to generate ASCII plot: {e}", exc_info=True)
            raise

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
