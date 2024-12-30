import backtrader as bt
import pandas as pd
import asciichartpy
import logging
from typing import Dict
import random


class Backtester:
    """
    Handles the execution of backtests, scenario testing, and synthetic data generation.
    """

    def __init__(self, strategy_manager, budget_manager):
        self.strategy_manager = strategy_manager
        self.budget_manager = budget_manager
        self.logger = logging.getLogger(self.__class__.__name__)

    def _convert_dataframe_to_bt_feed(self, historical_data: pd.DataFrame) -> bt.feeds.PandasData:
        """
        Converts a Pandas DataFrame to a Backtrader-compatible data feed.
        """
        required_columns = {"timestamp", "open", "high", "low", "close", "volume"}
        if not required_columns.issubset(historical_data.columns):
            raise ValueError(f"Missing required columns in DataFrame: {required_columns - set(historical_data.columns)}")

        historical_data['timestamp'] = pd.to_datetime(historical_data['timestamp'])
        historical_data.set_index('timestamp', inplace=True)

        return bt.feeds.PandasData(dataname=historical_data)

    def _create_bt_strategy(self, strategy: Dict):
        """
        Dynamically generates a Backtrader strategy from a strategy configuration.
        """
        parameters = strategy['data']['parameters']
        entry_conditions = strategy['data']['entry_conditions']
        exit_conditions = strategy['data']['exit_conditions']

        class GeneratedStrategy(bt.Strategy):
            params = parameters

            def __init__(self):
                self.order = None

            def next(self):
                if not self.position:
                    if eval(entry_conditions):
                        self.buy(size=self.params.get('position_size', 1))
                else:
                    if eval(exit_conditions):
                        self.sell(size=self.params.get('position_size', 1))

        return GeneratedStrategy

    def run_backtest(self, strategy_id: str, historical_data: pd.DataFrame):
        """
        Runs a backtest for the provided strategy using the given historical data.
        :param strategy_id: The ID of the strategy to backtest.
        :param historical_data: A Pandas DataFrame containing historical OHLCV data.
        """
        try:
            cerebro = bt.Cerebro()

            # Load historical data into Backtrader
            data = self._convert_dataframe_to_bt_feed(historical_data)
            cerebro.adddata(data)

            # Retrieve strategy
            strategy = self.strategy_manager.load_strategy(strategy_id)
            if not strategy:
                raise ValueError(f"Strategy with ID '{strategy_id}' does not exist.")

            # Extract key components from strategy data
            data = strategy.get('data', {})
            parameters = data.get('parameters', {})
            entry_conditions = data.get('entry_conditions', [])
            exit_conditions = data.get('exit_conditions', [])

            # Log warnings for missing components
            if not parameters:
                self.logger.warning(f"Strategy {strategy_id} has no 'parameters'.")
            if not entry_conditions:
                self.logger.warning(f"Strategy {strategy_id} has no 'entry_conditions'.")
            if not exit_conditions:
                self.logger.warning(f"Strategy {strategy_id} has no 'exit_conditions'.")

            # Set the initial cash
            starting_cash = self.budget_manager.get_budget(strategy_id) or 100000.0
            cerebro.broker.set_cash(starting_cash)

            # Add strategy to Backtrader
            bt_strategy = self._create_bt_strategy(parameters, entry_conditions, exit_conditions)
            cerebro.addstrategy(bt_strategy)

            # Print initial portfolio value
            print(f"Starting Portfolio Value: {cerebro.broker.getvalue():.2f} USDT")
            cerebro.run()

            # Print final portfolio value
            print(f"Final Portfolio Value: {cerebro.broker.getvalue():.2f} USDT")

            # Plot results using ASCII
            self._plot_ascii_results(historical_data)
        except Exception as e:
            self.logger.error(f"Error during backtest: {e}")
            raise

    def display_backtest_summary(self, cerebro):
        """
        Displays a summary of the backtest results using ASCII charts.
        """
        values = [cerebro.broker.getvalue() for _ in range(10)]  # Simulate periodic values
        chart = asciichartpy.plot(values, {'height': 10})
        self.logger.info("\n[ASCII Chart of Portfolio Value]\n" + chart)

    def generate_synthetic_data(self, timeframe: str, duration_days: int, scenario: str = "neutral") -> pd.DataFrame:
        """
        Generates synthetic OHLCV data based on a given scenario.
        :param timeframe: The timeframe for the synthetic data (e.g., '1T', '5T').
        :param duration_days: The number of days for the synthetic data.
        :param scenario: The market scenario ('bullish', 'bearish', 'neutral').
        :return: A Pandas DataFrame with the synthetic OHLCV data.
        """
        try:
            # Convert timeframe to valid Pandas frequency
            if timeframe.endswith('m'):
                timeframe = timeframe.replace('m', 'min')  # e.g., '1m' -> '1T'

            # Calculate the number of periods
            freq_per_day = pd.Timedelta("1D") / pd.Timedelta(timeframe)
            num_points = int(duration_days * freq_per_day)

            # Ensure the range doesn't exceed allowable timestamps
            start_date = pd.Timestamp.now()
            data = {
                "timestamp": pd.date_range(start=start_date, periods=num_points, freq=timeframe),
                "open": [],
                "high": [],
                "low": [],
                "close": [],
                "volume": []
            }

            # Generate synthetic OHLCV data
            base_price = 100.0
            for _ in range(num_points):
                change = (
                    random.uniform(-1, 1) if scenario == "neutral"
                    else random.uniform(0, 2) if scenario == "bullish"
                    else random.uniform(-2, 0)
                )
                price = max(base_price + change, 1)
                high = price + random.uniform(0, 1)
                low = price - random.uniform(0, 1)
                close = price + random.uniform(-0.5, 0.5)
                volume = random.randint(100, 1000)

                data["open"].append(price)
                data["high"].append(high)
                data["low"].append(low)
                data["close"].append(close)
                data["volume"].append(volume)

            return pd.DataFrame(data)
        except Exception as e:
            self.logger.error(f"Failed to generate synthetic data: {e}")
            raise


    def run_scenario_test(self, strategy_id: str, scenario: str, timeframe: str, duration_days: int):
        """
        Runs a backtest with synthetic data based on a specific scenario.
        """
        try:
            strategy = self.strategy_manager.load_strategy(strategy_id)
            synthetic_data = self.generate_synthetic_data(timeframe, duration_days, scenario)
            self.run_backtest(strategy_id, synthetic_data)
        except Exception as e:
            self.logger.error(f"Error during scenario test: {e}")
            raise
        
    def _plot_ascii_results(self, historical_data: pd.DataFrame):
        """
        Visualizes backtest results using ASCII.
        :param historical_data: DataFrame containing the OHLCV data.
        """
        try:
            from asciichartpy import plot

            closes = historical_data['close'].tolist()
            ascii_chart = plot(closes, {"height": 20, "format": "{:>8.2f}"})
            print("Backtest Results:")
            print(ascii_chart)
        except Exception as e:
            self.logger.error(f"Failed to generate ASCII plot: {e}")
