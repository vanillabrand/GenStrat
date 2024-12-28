import backtrader as bt
import termplotlib as tpl
import numpy as np
import pandas as pd
import logging
from typing import Dict, Any
from datetime import datetime, timedelta

class Backtester:
    """
    Handles backtesting of trading strategies using Backtrader.
    """

    def __init__(self, strategy_manager, budget_manager):
        """
        Initializes the Backtester class.
        :param strategy_manager: Instance of StrategyManager.
        :param budget_manager: Instance of BudgetManager.
        """
        self.strategy_manager = strategy_manager
        self.budget_manager = budget_manager

        self.logger = logging.getLogger(self.__class__.__name__)

    def _convert_dataframe_to_bt_feed(self, historical_data: pd.DataFrame) -> bt.feeds.PandasData:
        """
        Converts a pandas DataFrame into a Backtrader-compatible data feed.
        :param historical_data: A pandas DataFrame containing OHLCV data.
        :return: Backtrader PandasData object.
        """
        try:
            data = bt.feeds.PandasData(dataname=historical_data)
            return data
        except Exception as e:
            self.logger.error(f"Failed to convert historical data to Backtrader feed: {e}")
            raise

    def _create_bt_strategy(self, strategy_data: Dict[str, Any]):
        """
        Dynamically generates a Backtrader strategy class based on user-defined strategy data.
        :param strategy_data: A dictionary containing the strategy configuration.
        :return: A Backtrader strategy class.
        """
        try:
            class DynamicStrategy(bt.Strategy):
                params = strategy_data["params"]

                def __init__(self):
                    self.entry_condition = strategy_data["entry"]
                    self.exit_condition = strategy_data["exit"]

                def next(self):
                    try:
                        if eval(self.entry_condition):
                            self.buy()
                        elif eval(self.exit_condition):
                            self.sell()
                    except Exception as e:
                        self.logger.error(f"Error evaluating strategy conditions: {e}")

            return DynamicStrategy
        except Exception as e:
            self.logger.error(f"Failed to create Backtrader strategy: {e}")
            raise

    def _generate_ascii_graph(self, timestamps: list, portfolio_values: list):
        """
        Generates an ASCII graph for portfolio performance using termplotlib.
        :param timestamps: List of time points (e.g., dates).
        :param portfolio_values: List of portfolio values over time.
        """
        try:
            fig = tpl.figure()
            x_ticks = np.arange(0, len(timestamps), max(1, len(timestamps) // 10))
            fig.plot(
                range(len(portfolio_values)),
                portfolio_values,
                xlabel="Time",
                ylabel="Portfolio Value (USDT)",
                xlim=(0, len(portfolio_values) - 1),
                xticks=x_ticks,
                grid=True,
            )
            fig.show()
        except Exception as e:
            self.logger.error(f"Failed to generate ASCII graph: {e}")

    def calculate_metrics(self, cerebro: bt.Cerebro):
        """
        Calculate performance metrics like Sharpe ratio, max drawdown, etc.
        :param cerebro: Backtrader Cerebro instance.
        :return: Dictionary of calculated metrics.
        """
        metrics = {}
        try:
            metrics["final_value"] = cerebro.broker.getvalue()
            # Add more performance metrics as needed
        except Exception as e:
            self.logger.error(f"Failed to calculate metrics: {e}")
        return metrics
    
    def run_scenario_test(self, strategy_id: str, scenario: str, timeframe: str, duration_days: int):
            """
            Runs a backtest for a given strategy under a specified market scenario.
            :param strategy_id: ID of the strategy to test.
            :param scenario: The market scenario to simulate.
            :param timeframe: Time interval for synthetic data (e.g., '1m', '5m').
            :param duration_days: Duration of the synthetic data in days.
            """
            try:
                synthetic_data = SyntheticDataGenerator.generate_synthetic_data(scenario, timeframe, duration_days)
                self.run_backtest(strategy_id, synthetic_data)
            except Exception as e:
                print(f"Error during scenario testing: {e}")
                
    def run_backtest(self, strategy_id: str, historical_data: pd.DataFrame):
        """
        Runs a backtest for the provided strategy using the given historical data.
        :param strategy_id: The ID of the strategy to backtest.
        :param historical_data: A pandas DataFrame containing historical OHLCV data.
        """
        try:
            cerebro = bt.Cerebro()

            # Load historical data
            data = self._convert_dataframe_to_bt_feed(historical_data)
            cerebro.adddata(data)

            # Retrieve strategy and budget
            strategy = self.strategy_manager.load_strategy(strategy_id)
            starting_cash = self.budget_manager.get_budget(strategy_id) or 100000.0

            cerebro.broker.set_cash(starting_cash)

            # Add strategy to Backtrader
            bt_strategy = self._create_bt_strategy(strategy["data"])
            cerebro.addstrategy(bt_strategy)

            # Run backtest
            initial_value = cerebro.broker.getvalue()
            print(f"Starting Portfolio Value: {initial_value:.2f} USDT")

            cerebro.run()

            final_value = cerebro.broker.getvalue()
            print(f"Final Portfolio Value: {final_value:.2f} USDT")

            # Generate ASCII graph for portfolio performance
            timestamps = historical_data.index.to_list()
            portfolio_values = [initial_value, final_value]  # Example placeholder
            self._generate_ascii_graph(timestamps, portfolio_values)

        except Exception as e:
            self.logger.error(f"Error during backtest: {e}")
            print(f"Error during backtest: {e}")

    def generate_synthetic_data(self, scenario: str, timeframe: str, duration_days: int) -> pd.DataFrame:
            """
            Generates synthetic market data based on the selected scenario.
            :param scenario: The type of market scenario ('bull', 'bear', 'sideways', 'high_volatility', 'low_volatility').
            :param timeframe: Time interval (e.g., '1m', '5m', '1h').
            :param duration_days: Number of days to simulate.
            :return: A pandas DataFrame with OHLCV data.
            """
            timeframe_map = {"1m": 1, "5m": 5, "1h": 60}
            interval_minutes = timeframe_map.get(timeframe, 1)
            num_data_points = (duration_days * 24 * 60) // interval_minutes

            dates = [datetime.now() - timedelta(minutes=interval_minutes * i) for i in range(num_data_points)]
            dates.reverse()

            base_price = 100  # Starting price
            prices = []

            if scenario == "bull":
                prices = [base_price + i * 0.1 for i in range(num_data_points)]
            elif scenario == "bear":
                prices = [base_price - i * 0.1 for i in range(num_data_points)]
            elif scenario == "sideways":
                prices = [base_price + np.sin(i / 10) for i in range(num_data_points)]
            elif scenario == "high_volatility":
                prices = [base_price + np.random.uniform(-5, 5) for i in range(num_data_points)]
            elif scenario == "low_volatility":
                prices = [base_price + np.random.uniform(-1, 1) for i in range(num_data_points)]
            else:
                raise ValueError("Invalid scenario. Choose from 'bull', 'bear', 'sideways', 'high_volatility', 'low_volatility'.")

            data = {
                "timestamp": dates,
                "open": prices,
                "high": [p + np.random.uniform(0, 2) for p in prices],
                "low": [p - np.random.uniform(0, 2) for p in prices],
                "close": prices,
                "volume": [np.random.randint(100, 1000) for _ in range(num_data_points)]
            }
            return pd.DataFrame(data)
