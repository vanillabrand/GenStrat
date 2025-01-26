# System imports
import logging
import random
import json
from typing import Dict, List, Any, Optional, Type
from functools import lru_cache
from multiprocessing import Pool
from datetime import datetime
import asyncio

# Data processing
import pandas as pd
import numpy as np

# Trading framework
import backtrader as bt
from backtrader import Order
from backtrader.analyzers import (
    SharpeRatio,
    DrawDown,
    TradeAnalyzer,
    Returns,
    TimeReturn
)
from backtrader.feeds import PandasData

# Visualization
import asciichartpy
from rich.console import Console
from rich.table import Table
from rich.progress import Progress

# Custom managers
from trade_suggestion_manager import TradeSuggestionManager
from strategy_manager import StrategyManager
from budget_manager import BudgetManager
from risk_manager import RiskManager





class Backtester:
    """
    Handles the execution of backtests, scenario testing, and synthetic data generation.
    """

    def __init__(self, strategy_manager, budget_manager, risk_manager, trade_suggestion_manager):
        self.strategy_manager = strategy_manager
        self.budget_manager = budget_manager
        self.risk_manager = risk_manager
        self.trade_suggestion_manager = trade_suggestion_manager  # Replace TradeGenerator with TradeSuggestionManager
        self.logger = logging.getLogger(self.__class__.__name__)
        self.console = Console()

    def _validate_and_convert_data(self, historical_data: pd.DataFrame) -> bt.feeds.PandasData:
        """
        Validates and converts historical data into a Backtrader-compatible feed.
        """
        required_columns = {"timestamp", "open", "high", "low", "close", "volume"}
        missing_cols = required_columns - set(historical_data.columns)
        if missing_cols:
            raise ValueError(f"Missing required columns in DataFrame: {missing_cols}")

        # Ensure timestamp is a datetime index
        historical_data['timestamp'] = pd.to_datetime(historical_data['timestamp'])
        historical_data.set_index('timestamp', inplace=True)

        return bt.feeds.PandasData(dataname=historical_data)

    @lru_cache(maxsize=10)
    async def _load_strategy(self, strategy_id: str) -> Dict[str, Any]:
        """
        Loads strategy data asynchronously.
        """
        try:
            strategy = self.strategy_manager.load_strategy(strategy_id)
            if not strategy:
                raise ValueError(f"Strategy {strategy_id} not found.")
            return strategy
        except Exception as e:
            self.logger.error(f"Failed to load strategy: {e}")
            raise

        
    async def generate_synthetic_data(self, scenario="sideways", timeframe="1m", duration_days=1) -> pd.DataFrame:
            """
            Generates synthetic market data asynchronously.
            """
            try:
                frequency_map = {"1m": "min", "5m": "5min","10m": "10min", "1h": "h", "1d": "D", "1w": "W"}
                freq = frequency_map.get(timeframe, "min")
                num_points = (duration_days * 24 * 60) // int(timeframe[:-1])
                timestamps = pd.date_range(start="2023-01-01", periods=num_points, freq=freq)

                base_price = 100
                prices = []
                volumes = []

                for _ in range(num_points):
                    if scenario == "bull":
                        base_price += random.uniform(0.1, 1)
                    elif scenario == "bear":
                        base_price -= random.uniform(0.1, 1)
                    else:
                        base_price += random.uniform(-0.5, 0.5)

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

                self.logger.info(f"Synthetic data generated for scenario: {scenario}")
                return data

            except Exception as e:
                self.logger.error(f"Error generating synthetic data: {e}")
                raise

    def _simulate_market_data(self, historical_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Simulates fetching market data from historical data.
        """
        latest_data = historical_data.iloc[-1].to_dict()
        return {
            "current_price": latest_data["close"],
            "high": latest_data["high"],
            "low": latest_data["low"],
            "volume": latest_data["volume"],
        }

    def _validate_trade(self, trade: Dict[str, Any], strategy_data: Dict[str, Any]) -> bool:
        """
        Validates a trade based on strategy rules and risk management.
        """
        try:
            entry_price = trade.get("price")
            stop_loss = trade.get("stop_loss")
            strategy_name = strategy_data.get("strategy_name", "Unnamed Strategy")

            if entry_price is None or stop_loss is None:
                raise ValueError(f"Missing required trade fields: entry_price or stop_loss.")

            return self.risk_manager.validate_trade_risk(
                strategy_name=strategy_name,
                account_balance=self.budget_manager.get_budget(strategy_data["id"]),
                entry_price=entry_price,
                stop_loss=stop_loss
            )
        except Exception as e:
            self.logger.error(f"Trade validation failed: {e}")
            return False

    def _validate_trades_parallel(self, trades: List[Dict[str, Any]], strategy_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Validate trades in parallel using process pool."""
        try:
            with Pool(processes=4) as pool:
                results = pool.starmap(
                    self._validate_trade,
                    [(trade, strategy_data) for trade in trades]
                )
            return [trade for trade, valid in zip(trades, results) if valid]
        except Exception as e:
            self.logger.error(f"Trade validation failed: {e}")
            return []

    def _initialize_cerebro(self, historical_data: pd.DataFrame, starting_cash: float) -> bt.Cerebro:
        """Sets up and initializes the Cerebro engine synchronously."""
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
            self.logger.error(f"Failed to initialize Cerebro: {e}")
            raise

    async def run_backtest(self, strategy_id: str, historical_data: pd.DataFrame) -> Dict[str, Any]:

            """
            Runs a backtest with proper async handling.
            """
            if not strategy_id or not historical_data.size:
                raise ValueError("Invalid strategy_id or historical_data.")

            try:
                # Pre-validate and fetch market data
                enriched_data = await self.pre_validate_and_fetch_prices(strategy_id)
                strategy_data = enriched_data["strategy"]
                market_data = enriched_data["market_data"]

                # Get budget and starting cash
                budget = self.budget_manager.get_budget(strategy_id)
                starting_cash = float(budget or 100000.0)

                # Generate trade suggestions
                trade_suggestions = await self.trade_suggestion_manager.generate_trades(
                    strategy_json=strategy_data,
                    market_data=market_data,
                    budget=starting_cash,
                )

                # Validate trades in parallel
                valid_trades = self._validate_trades_parallel(trade_suggestions, strategy_data)
                if not valid_trades:
                    raise ValueError("No valid trades generated.")

                # Initialize and run backtest
                cerebro = self._initialize_cerebro(historical_data, starting_cash)
                strategy = self._create_bt_strategy(strategy_data, valid_trades)
                cerebro.addstrategy(strategy)

                # Add analyzers
                cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharperatio")
                cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
                cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
                cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")

                results = cerebro.run()
                if not results:
                    raise ValueError("Backtest produced no results.")

                return self._process_results(results[0])

            except Exception as e:
                self.logger.error(f"Backtest failed: {e}")
                raise

    async def pre_validate_and_fetch_prices(self, strategy_id: str) -> Dict:
            """
            Pre-validates the strategy and fetches market data.
            """
            try:
                strategy = await self._load_strategy(strategy_id)  # Ensure this is awaited
                assets = strategy.get("assets", [])

                if not assets:
                    raise ValueError("Strategy has no defined assets.")

                market_data = {}
                for asset in assets:
                    try:
                        ticker = await self.exchange.fetch_ticker(asset)
                        market_info = await self.exchange.fetch_market(asset)

                        market_data[asset] = {
                            "ticker": ticker,
                            "market_info": market_info,
                            "limits": market_info.get("limits", {}),
                            "precision": market_info.get("precision", {}),
                        }

                        await asyncio.sleep(0.1)  # Rate limiting

                    except Exception as e:
                        self.logger.error(f"Error fetching data for asset {asset}: {e}")
                        continue

                if not market_data:
                    raise ValueError("Failed to fetch any market data.")

                return {
                    "strategy": strategy,
                    "market_data": market_data,
                }

            except Exception as e:
                self.logger.error(f"Pre-validation failed: {e}")
                raise

    async def _fetch_market_data(self, strategy_data: Dict[str, Any]) -> Dict[str, Any]:
        """Fetches market data from exchange for strategy assets."""
        try:
            # Extract assets from strategy
            assets = strategy_data.get('assets', [])
            if not assets:
                raise ValueError("No assets defined in strategy")

            # Initialize market data structure
            market_data = {
                'exchange': self.exchange,
                'markets': {}
            }

            # Fetch data for each asset
            for asset in assets:
                try:
                    # Get ticker data
                    ticker = await self.exchange.fetch_ticker(asset)
                    
                    # Get market info
                    markets = await self.exchange.fetch_markets()
                    market_info = next((m for m in markets if m['symbol'] == asset), {})
                    
                    # Structure market data
                    market_data['markets'][asset] = {
                        'current_price': ticker['last'],
                        'high': ticker['high'],
                        'low': ticker['low'],
                        'volume': ticker['baseVolume'],
                        'limits': market_info.get('limits', {}),
                        'precision': market_info.get('precision', {}),
                        'market_type': market_info.get('type', 'spot'),
                        'leverage': market_info.get('leverage', None)
                    }
                    
                    # Add rate limiting delay
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    self.logger.error(f"Error fetching data for {asset}: {e}")
                    continue

            return market_data

        except Exception as e:
            self.logger.error(f"Market data fetch failed: {e}")
            raise


    def _prepare_parameters_from_strategy(self, strategy_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepares parameters from the strategy data for use in Backtrader strategies.
        :param strategy_data: The strategy data dictionary.
        :return: A dictionary containing the prepared parameters.
        """
        try:
            # Handle nested strategy data
            if "data" in strategy_data:
                strategy_data = strategy_data["data"]

            trade_parameters = strategy_data.get("trade_parameters", {})
            entry_conditions = strategy_data.get("conditions", {}).get("entry", [])
            exit_conditions = strategy_data.get("conditions", {}).get("exit", [])

            self.logger.info(f"Entry and Exit Conditions: {entry_conditions}, {exit_conditions}")

            if not entry_conditions:
                raise ValueError("No entry conditions defined in the strategy.")

            if not exit_conditions:
                self.logger.warning("No exit conditions defined in the strategy.")

            return {
                "trade_parameters": trade_parameters,
                "entry_conditions": entry_conditions,
                "exit_conditions": exit_conditions
            }
        except Exception as e:
            self.logger.error(f"Error preparing parameters from strategy: {e}")
            raise

    def _process_results(self, results) -> Dict[str, Any]:
        """Process backtest results safely."""
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

            if stats['total_trades'] > 0:
                stats['win_rate'] = (stats['won_trades'] / stats['total_trades']) * 100
            else:
                stats['win_rate'] = 0.0

            return stats

        except Exception as e:
            self.logger.error(f"Error processing results: {e}")
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

    def _generate_summary_table(self, initial_value: float, final_value: float, results: List[Any]):
        """
        Generates a summary table for the backtest results.
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
        Visualizes backtest results using ASCII with real-time updates.
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
        """Validate strategy with market data."""
        try:
            enriched_data = await self.backtester.pre_validate_and_fetch_prices(strategy_id)
            return enriched_data
        except Exception as e:
            self.logger.error(f"Strategy validation failed: {e}")
            raise