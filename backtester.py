import pandas as pd
import asciichartpy
import logging
import random
from rich.console import Console
from rich.table import Table
from rich.progress import Progress
from typing import Dict, List, Any, Optional
from functools import lru_cache
from multiprocessing import Pool
from trade_suggestion_manager import TradeSuggestionManager  # Import new manager
import json
import backtrader as bt
from backtrader.analyzers import (
    SharpeRatio,
    DrawDown,
    TradeAnalyzer,
    Returns,
    TimeReturn,
    PositionsValue
)
from backtrader.feeds import PandasData



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
        """Load strategy with async support."""
        try:
            strategy = await self.strategy_manager.load_strategy(strategy_id)
            if not strategy:
                raise ValueError(f"Strategy {strategy_id} not found")
            return strategy
        except Exception as e:
            self.logger.error(f"Failed to load strategy: {e}")
            raise
    
    def generate_synthetic_data(self, scenario="sideways", timeframe="1m", duration_days=1):
        """
        Generates synthetic market data for testing based on the given scenario.
        """
        try:
            # Map timeframes to pandas frequency codes
            frequency_map = {"1m": "min", "5m": "5min", "1h": "H", "1d": "D"}
            freq = frequency_map.get(timeframe, "min")
            num_points = (duration_days * 24 * 60) // int(timeframe[:-1])
            timestamps = pd.date_range(start="2023-01-01", periods=num_points, freq=freq)

            base_price = 100
            prices = []
            volumes = []

            for _ in range(num_points):
                if scenario == "bull":
                    base_price += random.uniform(0.1, 1)  # Gradual upward trend
                elif scenario == "bear":
                    base_price -= random.uniform(0.1, 1)  # Gradual downward trend
                elif scenario == "sideways" or scenario is None:
                    base_price += random.uniform(-0.5, 0.5)  # Random fluctuations
                else:
                    self.logger.warning(f"Unknown scenario '{scenario}' provided. Defaulting to 'sideways'.")
                    base_price += random.uniform(-0.5, 0.5)

                base_price = max(base_price, 1)  # Prevent negative prices
                prices.append(base_price)
                volumes.append(random.randint(100, 1000))

            # Generate high, low, open, close prices
            open_prices = prices[:-1] + [prices[-1]]
            close_prices = prices
            high_prices = [max(o, c) + random.uniform(0, 0.5) for o, c in zip(open_prices, close_prices)]
            low_prices = [min(o, c) - random.uniform(0, 0.5) for o, c in zip(open_prices, close_prices)]

            data = pd.DataFrame({
                "timestamp": timestamps,
                "open": open_prices,
                "high": high_prices,
                "low": low_prices,
                "close": close_prices,
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

    def _parallel_validate_trades(self, trades: List[Dict[str, Any]], strategy_data: Dict[str, Any]) -> List[Dict[str, Any]]:
            """
            Validates trades in parallel.
            """
            with Pool(processes=4) as pool:
                results = pool.starmap(
                    self._validate_trade,
                    [(trade, strategy_data) for trade in trades]
                )
            return [trade for trade, valid in zip(trades, results) if valid]

    def _initialize_cerebro(self, historical_data: pd.DataFrame, strategy_data: Dict[str, Any]) -> bt.Cerebro:
        """
        Sets up and initializes the Cerebro engine.
        """
        cerebro = bt.Cerebro()
        data_feed = self._validate_and_convert_data(historical_data)
        cerebro.adddata(data_feed)

        starting_cash = self.budget_manager.get_budget(strategy_data['id']) or 100000.0
        cerebro.broker.set_cash(starting_cash)

        # Prepare parameters for the strategy
        params = self._prepare_parameters_from_strategy(strategy_data)
        bt_strategy = self._create_bt_strategy(
            params["trade_parameters"],
            params["entry_conditions"],
            params["exit_conditions"]
        )
        cerebro.addstrategy(bt_strategy)
        return cerebro

    async def pre_validate_and_fetch_prices(self, strategy_id: str) -> Dict:
        """
        Pre-validates the strategy and fetches market data for its assets.
        :param strategy_id: The ID of the strategy to validate.
        :return: A dictionary with strategy JSON and enriched market data.
        """
        try:
            # Load strategy
            strategy = self._load_strategy(strategy_id)
            assets = strategy.get("assets", [])
            if not assets:
                raise ValueError("Strategy has no defined assets.")

            # Fetch market data for the assets
            self.logger.info(f"Fetching market data for assets: {assets}")
            market_data = await self.trade_generator.fetch_market_data(assets)
            if not market_data:
                raise ValueError("Failed to fetch market data for assets.")

            # Enrich strategy data with market data
            enriched_strategy_data = {
                "strategy": strategy,
                "market_data": market_data
            }
            self.logger.info(f"Pre-validation and market data fetch completed.")
            return enriched_strategy_data
        except Exception as e:
            self.logger.error(f"Error during pre-validation: {e}")
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
                "exit_conditions": exit_conditions,
            }
        except Exception as e:
            self.logger.error(f"Error preparing parameters from strategy: {e}")
            raise

        
    async def run_backtest(self, strategy_id: str, historical_data: pd.DataFrame) -> Dict[str, Any]:
        """Runs a backtest with proper async handling."""
        try:
            # Load and validate strategy
            strategy_data = await self._load_strategy(strategy_id)
            if not strategy_data:
                raise ValueError(f"Strategy {strategy_id} not found")

            # Initialize Cerebro
            cerebro = self._initialize_cerebro(historical_data, strategy_data)
            
            # Add analyzers
            cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharperatio')
            cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
            cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
            cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')

            # Run backtest
            results = cerebro.run()
            if not results:
                raise ValueError("Backtest produced no results")

            # Process results
            stats = self._process_results(results[0])
            self._generate_summary_table(stats)
            
            return stats

        except Exception as e:
            self.logger.error(f"Backtest failed: {str(e)}", exc_info=True)
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
            return {}       

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

    def _create_bt_strategy(
        self,
        trade_parameters: Dict[str, Any],
        entry_conditions: List[Dict[str, Any]],
        exit_conditions: List[Dict[str, Any]]
    ):
        """
        Dynamically generates a Backtrader strategy from a strategy configuration.
        """

        class GeneratedStrategy(bt.Strategy):
            params = trade_parameters

            def __init__(self):
                self.order = None
                self.logger = logging.getLogger(self.__class__.__name__)
                self.conditions_cache = {}

            def evaluate_conditions(self, conditions: List[Dict[str, Any]]) -> bool:
                conditions_key = str(conditions)
                if conditions_key in self.conditions_cache:
                    return self.conditions_cache[conditions_key]

                try:
                    result = all(cond["value"] for cond in conditions)
                    self.conditions_cache[conditions_key] = result
                    return result
                except KeyError as e:
                    self.logger.error(f"Condition evaluation error: {e}")
                    return False

            def next(self):
                self.logger.debug(f"Next called. Current Position: {self.position.size}")
                self.logger.debug(f"Cash: {self.broker.get_cash()}, Value: {self.broker.get_value()}")

                if not self.position:
                    if self.evaluate_conditions(entry_conditions):
                        size = self.params.get('position_size', 1)
                        side = self.params.get('side', 'long')
                        entry_price = self.data.close[0]
                        stop_loss = self.params.get('stop_loss', None)

                        if stop_loss:
                            stop_loss_price = self.params['risk_manager'].calculate_stop_loss(entry_price, stop_loss / 100)

                        if side == 'long':
                            self.order = self.buy(size=size)
                            self.logger.info(f"Long buy order placed. Size: {size}")
                        elif side == 'short':
                            self.order = self.sell(size=size)
                            self.logger.info(f"Short sell order placed. Size: {size}")

                elif self.evaluate_conditions(exit_conditions):
                    if self.position.size > 0:
                        self.order = self.sell(size=self.params.get('position_size', 1))
                        self.logger.info(f"Closing long position.")
                    elif self.position.size < 0:
                        self.order = self.buy(size=self.params.get('position_size', 1))
                        self.logger.info(f"Closing short position.")

        return GeneratedStrategy
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

    def _create_bt_strategy(
            
        self,
        trade_parameters: Dict[str, Any],
        entry_conditions: List[Dict[str, Any]],
        exit_conditions: List[Dict[str, Any]]
    ):
        """
        Dynamically generates a Backtrader strategy from a strategy configuration.
        """

        class GeneratedStrategy(bt.Strategy):
            params = trade_parameters

            def __init__(self):
                self.order = None
                self.logger = logging.getLogger(self.__class__.__name__)
                self.conditions_cache = {}

            def evaluate_conditions(self, conditions: List[Dict[str, Any]]) -> bool:
                conditions_key = str(conditions)
                if conditions_key in self.conditions_cache:
                    return self.conditions_cache[conditions_key]

                try:
                    result = all(cond["value"] for cond in conditions)
                    self.conditions_cache[conditions_key] = result
                    return result
                except KeyError as e:
                    self.logger.error(f"Condition evaluation error: {e}")
                    return False

            def next(self):
                self.logger.debug(f"Next called. Current Position: {self.position.size}")
                self.logger.debug(f"Cash: {self.broker.get_cash()}, Value: {self.broker.get_value()}")

                if not self.position:
                    if self.evaluate_conditions(entry_conditions):
                        size = self.params.get('position_size', 1)
                        side = self.params.get('side', 'long')
                        entry_price = self.data.close[0]
                        stop_loss = self.params.get('stop_loss', None)

                        if stop_loss:
                            stop_loss_price = self.params['risk_manager'].calculate_stop_loss(entry_price, stop_loss / 100)

                        if side == 'long':
                            self.order = self.buy(size=size)
                            self.logger.info(f"Long buy order placed. Size: {size}")
                        elif side == 'short':
                            self.order = self.sell(size=size)
                            self.logger.info(f"Short sell order placed. Size: {size}")

                elif self.evaluate_conditions(exit_conditions):
                    if self.position.size > 0:
                        self.order = self.sell(size=self.params.get('position_size', 1))
                        self.logger.info(f"Closing long position.")
                    elif self.position.size < 0:
                        self.order = self.buy(size=self.params.get('position_size', 1))
                        self.logger.info(f"Closing short position.")

        return GeneratedStrategy
    