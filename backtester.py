import backtrader as bt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


class Backtester:
    """
    A class to handle backtesting of trading strategies with both historical and synthetic data using Backtrader.
    """

    def __init__(self, strategy_manager, budget_manager):
        """
        Initializes the backtester with a reference to the strategy manager and budget manager.
        :param strategy_manager: An instance of StrategyManager to retrieve strategy data.
        :param budget_manager: An instance of BudgetManager to retrieve allocated budgets.
        """
        self.strategy_manager = strategy_manager
        self.budget_manager = budget_manager

    def run_backtest(self, strategy_id, historical_data):
        """
        Runs a backtest for the provided strategy using the given historical data.
        :param strategy_id: The ID of the strategy to backtest.
        :param historical_data: A pandas DataFrame containing historical OHLCV data.
        """
        try:
            cerebro = bt.Cerebro()

            # Load the historical data into Backtrader
            data = self._convert_dataframe_to_bt_feed(historical_data)
            cerebro.adddata(data)

            # Retrieve strategy and budget
            strategy = self.strategy_manager.load_strategy(strategy_id)
            starting_cash = self.budget_manager.get_budget(strategy_id)
            if starting_cash is None:
                starting_cash = 100000.0  # Default value if no budget is set

            cerebro.broker.set_cash(starting_cash)

            # Dynamically generate and add strategy
            bt_strategy = self._create_bt_strategy(strategy)
            cerebro.addstrategy(bt_strategy)

            print(f"Starting Portfolio Value: {cerebro.broker.getvalue():.2f} USDT")
            cerebro.run()
            print(f"Final Portfolio Value: {cerebro.broker.getvalue():.2f} USDT")

            # Plot the results
            cerebro.plot()
        except Exception as e:
            print(f"Error during backtest: {e}")

    def generate_synthetic_data(self, timeframe: str, duration: int) -> pd.DataFrame:
        """
        Generates synthetic OHLCV data for backtesting.
        :param timeframe: The timeframe for the data (e.g., '1m', '5m', '1h', '1d').
        :param duration: Duration in days for which the data is generated.
        :return: A pandas DataFrame containing synthetic OHLCV data.
        """
        interval_minutes = self._parse_timeframe_to_minutes(timeframe)
        end_time = datetime.now()
        start_time = end_time - timedelta(days=duration)
        total_intervals = int((end_time - start_time).total_seconds() / 60 / interval_minutes)

        # Generate timestamps
        timestamps = [start_time + timedelta(minutes=i * interval_minutes) for i in range(total_intervals)]

        # Generate synthetic OHLCV data
        prices = self._generate_price_series(total_intervals)
        open_prices, high_prices, low_prices, close_prices = self._generate_ohlc(prices)
        volumes = self._generate_volumes(total_intervals)

        synthetic_data = pd.DataFrame({
            'datetime': timestamps,
            'open': open_prices,
            'high': high_prices,
            'low': low_prices,
            'close': close_prices,
            'volume': volumes
        })
        synthetic_data.set_index('datetime', inplace=True)
        return synthetic_data

    def _convert_dataframe_to_bt_feed(self, df: pd.DataFrame) -> bt.feeds.PandasData:
        """
        Converts a pandas DataFrame to a Backtrader-compatible data feed.
        :param df: The pandas DataFrame with OHLCV data.
        :return: A Backtrader data feed.
        """
        return bt.feeds.PandasData(dataname=df)

    def _create_bt_strategy(self, strategy):
        """
        Dynamically creates a Backtrader strategy class from the given strategy.
        :param strategy: A dictionary containing the strategy's logic and parameters.
        :return: A dynamically generated Backtrader strategy class.
        """
        class DynamicStrategy(bt.Strategy):
            params = strategy['parameters']

            def __init__(self):
                self.indicators = []
                for indicator in strategy['indicators']:
                    func = getattr(bt.indicators, indicator['name'])
                    params = indicator.get('params', {})
                    self.indicators.append(func(self.data, **params))

            def next(self):
                # Entry condition
                if all(indicator[0] for indicator in self.indicators):
                    self.buy(size=self.params.get('size', 1))

                # Exit condition
                if any(indicator[1] for indicator in self.indicators):
                    self.sell(size=self.params.get('size', 1))

        return DynamicStrategy

    def _parse_timeframe_to_minutes(self, timeframe: str) -> int:
        if timeframe.endswith('m'):
            return int(timeframe[:-1])
        elif timeframe.endswith('h'):
            return int(timeframe[:-1]) * 60
        elif timeframe.endswith('d'):
            return int(timeframe[:-1]) * 60 * 24
        else:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

    def _generate_price_series(self, total_intervals: int) -> np.ndarray:
        return np.cumprod(1 + np.random.normal(0, 0.01, total_intervals)) * 100

    def _generate_ohlc(self, prices: np.ndarray) -> tuple:
        open_prices = prices
        high_prices = open_prices + np.random.uniform(0.5, 2.0, len(prices))
        low_prices = open_prices - np.random.uniform(0.5, 2.0, len(prices))
        close_prices = prices + np.random.uniform(-1.0, 1.0, len(prices))
        return open_prices, high_prices, low_prices, close_prices

    def _generate_volumes(self, total_intervals: int) -> np.ndarray:
        return np.random.randint(100, 1000, total_intervals)
