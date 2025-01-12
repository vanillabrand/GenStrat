import backtrader as bt
import pandas as pd
import asciichartpy
import logging
from rich.console import Console
from rich.table import Table
from rich.progress import Progress
from typing import Dict, List, Any, Optional
import random
from functools import lru_cache
from multiprocessing import Pool


class Backtester:
    """
    Handles the execution of backtests, scenario testing, and synthetic data generation.
    """

    def __init__(self, strategy_manager, budget_manager, risk_manager, trade_generator):
        self.strategy_manager = strategy_manager
        self.budget_manager = budget_manager
        self.risk_manager = risk_manager
        self.trade_generator = trade_generator
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
    def _load_strategy(self, strategy_id: str) -> Dict[str, Any]:
        """
        Loads and caches strategy data by ID.
        """
        strategy = self.strategy_manager.load_strategy(strategy_id)
        if not strategy:
            raise ValueError(f"Strategy with ID '{strategy_id}' does not exist or is empty.")
        return strategy

    def _generate_and_validate_trades(self, strategy_data: Dict[str, Any], historical_data: pd.DataFrame):
        """
        Generates and validates trades in a single step.
        """
        trades = self.trade_generator.generate_trades(strategy_data, historical_data)
        return [
            trade for trade in trades
            if self.trade_generator.validate_trade(trade, strategy_data)
        ]

    def _parallel_validate_trades(self, trades: List[Dict[str, Any]], strategy_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Validates trades in parallel.
        """
        with Pool(processes=4) as pool:
            results = pool.starmap(
                self.trade_generator.validate_trade,
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

        params = self._prepare_parameters_from_strategy(strategy_data)
        bt_strategy = self._create_bt_strategy(
            params["trade_parameters"],
            params["entry_conditions"],
            params["exit_conditions"]
        )
        cerebro.addstrategy(bt_strategy)
        return cerebro

    def run_backtest(self, strategy_id: str, historical_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Runs a backtest for the provided strategy using the given historical data.
        :returns: Dictionary with backtest results, including final portfolio value.
        """
        try:
            # Validate historical data
            cerebro = self._initialize_cerebro(historical_data, self._load_strategy(strategy_id))

            # Real-time progress bar
            with Progress() as progress:
                task = progress.add_task("Running Backtest...", total=100)

                def update_progress():
                    progress.update(task, advance=1)

                cerebro.addwriter(update_progress)

                # Start Backtest
                initial_value = cerebro.broker.getvalue()
                self.logger.info(f"Starting Portfolio Value: {initial_value:.2f} USDT")
                print(f"Starting Portfolio Value: {initial_value:.2f} USDT")
                results = cerebro.run()

                final_value = cerebro.broker.getvalue()
                self.logger.info(f"Final Portfolio Value: {final_value:.2f} USDT")
                print(f"Final Portfolio Value: {final_value:.2f} USDT")

            self._generate_summary_table(initial_value, final_value, results)

            return {
                "initial_value": initial_value,
                "final_value": final_value,
                "results": results
            }
        except Exception as e:
            self.logger.error(f"Error during backtest: {e}", exc_info=True)
            raise

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
            params = trade_parameters  # This will hold your trade_parameters dict

            def __init__(self):
                self.order = None
                self.logger = logging.getLogger(self.__class__.__name__)
                self.conditions_cache = {}

            def evaluate_conditions(self, conditions: List[Dict[str, Any]]) -> bool:
                """
                Evaluates conditions and caches results to avoid redundant computation.
                """
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
                """
                Handles the next data point in the Backtrader loop.
                """
                self.logger.debug(f"Next called. Current Position: {self.position.size}")
                self.logger.debug(f"Cash: {self.broker.get_cash()}, Value: {self.broker.get_value()}")

                if not self.position:
                    if self.evaluate_conditions(entry_conditions):
                        size = self.params.get('position_size', 1)
                        side = self.params.get('side', 'long')
                        entry_price = self.data.close[0]
                        stop_loss = self.params.get('stop_loss', None)

                        if stop_loss:
                            stop_loss_price = self.risk_manager.calculate_stop_loss(entry_price, stop_loss / 100)
                        else:
                            stop_loss_price = None

                        if side == 'long':
                            self.order = self.buy(size=size)
                            self.logger.info(f"Long buy order placed. Size: {size}")
                            if stop_loss_price:
                                self.sell(size=size, exectype=bt.Order.Stop, price=stop_loss_price)
                                self.logger.info(f"Stop-loss set at {stop_loss_price}")
                        elif side == 'short':
                            self.order = self.sell(size=size)
                            self.logger.info(f"Short sell order placed. Size: {size}")
                            if stop_loss_price:
                                self.buy(size=size, exectype=bt.Order.Stop, price=stop_loss_price)
                                self.logger.info(f"Stop-loss set at {stop_loss_price}")

                else:
                    if self.evaluate_conditions(exit_conditions):
                        size = self.params.get('position_size', 1)
                        if self.position.size > 0:
                            self.order = self.sell(size=size)
                            self.logger.info(f"Closing long position. Size: {size}")
                        elif self.position.size < 0:
                            self.order = self.buy(size=size)
                            self.logger.info(f"Closing short position. Size: {size}")

        return GeneratedStrategy
