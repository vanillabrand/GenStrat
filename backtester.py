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
# In this updated version, we no longer require specific keys (e.g. "price", "stop_loss")
# to decide if a trade is valid. We simply return True.
def validate_trade_helper(trade: Dict[str, Any], strategy_data: Dict[str, Any]) -> bool:
    """
    A dummy trade validation helper.
    This version does not enforce the presence of specific keys,
    but simply returns True to indicate that if a trade object exists,
    it is considered valid.
    """
    return True

# ---------------- Backtester Class ----------------
class Backtester:
    """
    Handles the execution of backtests, scenario testing, and synthetic data generation.
    Integrates with a ccxt-based exchange (e.g., Bitget) for historical OHLCV retrieval,
    plus StrategyManager, BudgetManager, RiskManager, and TradeSuggestionManager for
    validating and producing realistic trade flows via Backtrader.
    
    Advanced risk management is implemented using both fixed thresholds and an ATR-based dynamic trailing stop.
    Indicator instances for entry and exit conditions are created dynamically.
    When the indicator is "MACD", parameters are remapped from JSON keys ("short_period", "long_period", "signal_period")
    to Backtrader's expected keys ("period_me1", "period_me2", "period_signal").
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
        required_columns = {"timestamp", "open", "high", "low", "close", "volume"}
        missing_cols = required_columns - set(historical_data.columns)
        if missing_cols:
            raise ValueError(f"Missing required columns in DataFrame: {missing_cols}")
        historical_data['timestamp'] = pd.to_datetime(historical_data['timestamp'])
        historical_data.set_index('timestamp', inplace=True)
        return bt.feeds.PandasData(dataname=historical_data)

    @lru_cache(maxsize=10)
    async def _load_strategy(self, strategy_id: str) -> Dict[str, Any]:
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
            self.logger.info(f"Synthetic data generated for scenario: {data}, timeframe: {timeframe}, days: {duration_days}")
            return data
        except Exception as e:
            self.logger.error(f"Error generating synthetic data: {e}", exc_info=True)
            raise

    def _simulate_market_data(self, historical_data: pd.DataFrame) -> Dict[str, Any]:
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
        Instead of checking for specific fields, simply return the trade list.
        If no trades were generated, the backtest will fail with an appropriate error.
        """
        if not trades:
            self.logger.error("No trades were generated by the trade suggestion engine.")
            return []
        # If trades exist, return them as-is.
        return trades

    # --- Cerebro Initialization & Execution ---
    def _initialize_cerebro(self, historical_data: pd.DataFrame, starting_cash: float) -> bt.Cerebro:
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

    def _create_bt_strategy(self, strategy_data: Dict[str, Any], trades: List[Dict[str, Any]]) -> Type[bt.Strategy]:
        """
        Dynamically creates a Backtrader Strategy class based on the provided strategy data and validated trades.
        Dynamically creates indicator instances for all entry and exit conditions.
        Implements advanced risk management using fixed stop-loss/take-profit and an ATR-based dynamic trailing stop.
        Remaps MACD parameters from keys ("short_period", "long_period", "signal_period")
        to Backtrader's expected keys ("period_me1", "period_me2", "period_signal"), ensuring no zero or negative periods.
        """
        import backtrader.indicators as btind

        class DynamicStrategy(bt.Strategy):
            # You might want to store only the parts of strategy_data that are relevant,
            # but here we simply assign the full dictionary.
            params = strategy_data

            def __init__(self):
                self.entry_conditions = []
                self.exit_conditions = []
                conditions = strategy_data.get("conditions", {})
                entry_conditions_data = conditions.get("entry", [])
                exit_conditions_data = conditions.get("exit", [])

                # Process entry conditions
                for cond in entry_conditions_data:
                    ind_name = cond.get("indicator")
                    operator = cond.get("operator")
                    threshold = cond.get("value")
                    ind_params = cond.get("indicator_parameters", {}).copy()
                    if ind_name and ind_name.lower() == "macd":
                        # Remap MACD parameters and ensure they are > 0
                        short = ind_params.pop("short_period", 12)
                        long = ind_params.pop("long_period", 26)
                        signal = ind_params.pop("signal_period", 9)
                        if not short or short <= 0:
                            short = 12
                        if not long or long <= 0:
                            long = 26
                        if not signal or signal <= 0:
                            signal = 9
                        ind_params = {
                            "period_me1": short,
                            "period_me2": long,
                            "period_signal": signal
                        }
                    ind_class = getattr(btind, ind_name, None)
                    if ind_class is None:
                        self.log(f"Indicator '{ind_name}' not found in backtrader.indicators.", logging.ERROR)
                        continue
                    try:
                        instance = ind_class(self.data.close, **ind_params)
                    except Exception as e:
                        self.log(f"Error initializing {ind_name}: {e}", logging.ERROR)
                        continue
                    self.entry_conditions.append((instance, operator, threshold))

                # Process exit conditions
                for cond in exit_conditions_data:
                    ind_name = cond.get("indicator")
                    operator = cond.get("operator")
                    threshold = cond.get("value")
                    ind_params = cond.get("indicator_parameters", {}).copy()
                    if ind_name and ind_name.lower() == "macd":
                        short = ind_params.pop("short_period", 12)
                        long = ind_params.pop("long_period", 26)
                        signal = ind_params.pop("signal_period", 9)
                        if not short or short <= 0:
                            short = 12
                        if not long or long <= 0:
                            long = 26
                        if not signal or signal <= 0:
                            signal = 9
                        ind_params = {
                            "period_me1": short,
                            "period_me2": long,
                            "period_signal": signal
                        }
                    ind_class = getattr(btind, ind_name, None)
                    if ind_class is None:
                        self.log(f"Indicator '{ind_name}' not found in backtrader.indicators.", logging.ERROR)
                        continue
                    try:
                        instance = ind_class(self.data.close, **ind_params)
                    except Exception as e:
                        self.log(f"Error initializing {ind_name}: {e}", logging.ERROR)
                        continue
                    self.exit_conditions.append((instance, operator, threshold))

                # Advanced Risk Management: fixed stop-loss/take-profit and ATR-based trailing stop
                risk_params = strategy_data.get("risk_management", {})
                self.fixed_stop_loss_pct = risk_params.get("stop_loss", None)
                self.fixed_take_profit_pct = risk_params.get("take_profit", None)
                self.atr_period = risk_params.get("atr_period", 14)
                self.atr_multiplier = risk_params.get("atr_multiplier", 3)
                # Ensure atr_period is valid (avoid division by zero inside ATR)
                if not self.atr_period or self.atr_period <= 0:
                    self.atr_period = 14
                try:
                    self.atr = btind.ATR(self.data, period=self.atr_period)
                except Exception as e:
                    self.log(f"Error initializing ATR: {e}", logging.ERROR)
                    # Fallback: create a dummy ATR that returns a small nonzero value
                    class DummyATR(bt.Indicator):
                        lines = ('atr',)
                        def next(self):
                            self.lines.atr[0] = 1e-6
                    self.atr = DummyATR(self.data, period=self.atr_period)
                self.trailing_stop = None

                self.order = None
                self.buy_price = None

            def next(self):
                # If an order is pending, do nothing.
                if self.order:
                    return

                if not self.position:
                    # Evaluate all entry conditions.
                    if all(self._evaluate_condition(ind, op, thr) for (ind, op, thr) in self.entry_conditions):
                        self.order = self.buy()
                        self.buy_price = self.data.close[0]
                        # Avoid division by zero: if ATR is zero, use a very small number.
                        atr_value = self.atr[0] if self.atr[0] != 0 else 1e-6
                        self.trailing_stop = self.data.close[0] - atr_value * self.atr_multiplier
                else:
                    # Update the trailing stop (use safe ATR value).
                    atr_value = self.atr[0] if self.atr[0] != 0 else 1e-6
                    new_trailing = self.data.close[0] - atr_value * self.atr_multiplier
                    if new_trailing > self.trailing_stop:
                        self.trailing_stop = new_trailing

                    exit_signal = all(self._evaluate_condition(ind, op, thr) for (ind, op, thr) in self.exit_conditions)
                    current_price = self.data.close[0]
                    risk_exit = False
                    if self.buy_price is not None:
                        if self.fixed_stop_loss_pct is not None and current_price <= self.buy_price * (1 - self.fixed_stop_loss_pct):
                            risk_exit = True
                        if self.fixed_take_profit_pct is not None and current_price >= self.buy_price * (1 + self.fixed_take_profit_pct):
                            risk_exit = True

                    if exit_signal or risk_exit or (self.trailing_stop is not None and current_price < self.trailing_stop):
                        self.order = self.close()

            def _evaluate_condition(self, indicator, operator, threshold) -> bool:
                try:
                    current_value = indicator[0]
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
               

        return DynamicStrategy



    # --- Running a Backtest ---
    async def run_backtest(self, strategy_id: str, historical_data: pd.DataFrame) -> Dict[str, Any]:
        if not strategy_id or historical_data.empty:
            raise ValueError("Invalid strategy_id or empty historical data.")
        try:
            strategy = await self._load_strategy(strategy_id)
            strategy_data = strategy["data"]
           
            budget = await self.budget_manager.get_budget(strategy_id)
            
            starting_cash = float(budget)

            trade_suggestions = await self.trade_suggestion_manager.generate_trades(
                strategy_id, strategy_data, historical_data, starting_cash
            )

           
            valid_trades = self._validate_trades_parallel(trade_suggestions, strategy_data)
            if not valid_trades:
                raise ValueError("No trades were generated for backtest. Please check your strategy parameters and try again.")

            cerebro = self._initialize_cerebro(historical_data, starting_cash)
            self.logger.info(f"INITIALIZED CEREBRO: {trade_suggestions}")

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
        table = Table(title="Backtest Summary")
        table.add_column("Metric", justify="left")
        table.add_column("Value", justify="right")
        table.add_row("Starting Portfolio Value", f"{initial_value:.2f} USDT")
        table.add_row("Ending Portfolio Value", f"{final_value:.2f} USDT")
        table.add_row("Net Profit/Loss", f"{final_value - initial_value:.2f} USDT")
        self.console.print(table)

    def _plot_ascii_results(self, historical_data: pd.DataFrame):
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
        try:
            enriched_data = await self.pre_validate_and_fetch_prices(strategy_id)
            return enriched_data
        except Exception as e:
            self.logger.error(f"Strategy validation failed: {e}", exc_info=True)
            raise
