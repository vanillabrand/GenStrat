import backtrader as bt
import pandas as pd
import asciichartpy
import logging
from typing import Dict, List, Any, Optional
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
        missing_cols = required_columns - set(historical_data.columns)
        if missing_cols:
            raise ValueError(f"Missing required columns in DataFrame: {missing_cols}")

        # Ensure timestamp is a datetime index
        historical_data['timestamp'] = pd.to_datetime(historical_data['timestamp'])
        historical_data.set_index('timestamp', inplace=True)

        return bt.feeds.PandasData(dataname=historical_data)

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

            def evaluate_conditions(self, conditions: List[Dict[str, Any]]) -> bool:
                """
                Evaluates the conditions dynamically.
                Replace the placeholder logic with your own condition checks.
                """
                # Example placeholder: each condition dict has a boolean under "value"
                try:
                    return all(cond["value"] for cond in conditions)
                except KeyError:
                    return False

            def next(self):
                """
                Handles the next data point in the Backtrader loop.
                """
                if not self.position:
                    # If no open position, check entry conditions
                    if self.evaluate_conditions(entry_conditions):
                        self.order = self.buy(size=self.params.get('position_size', 1))
                else:
                    # If in a position, check exit conditions
                    if self.evaluate_conditions(exit_conditions):
                        self.order = self.sell(size=self.params.get('position_size', 1))

        return GeneratedStrategy

    def run_backtest(self, strategy_id: str, historical_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Runs a backtest for the provided strategy using the given historical data.
        :returns: Dictionary with backtest results, including final portfolio value.
        """
        try:
            # 1) Set up Cerebro engine
            cerebro = bt.Cerebro()

            # 2) Convert DataFrame to Backtrader feed and add to Cerebro
            data_feed = self._convert_dataframe_to_bt_feed(historical_data)
            cerebro.adddata(data_feed)

            # 3) Retrieve and validate strategy from strategy_manager
            strategy = self.strategy_manager.load_strategy(strategy_id)
            # The updated StrategyManager raises an error if not found,
            # but let's double-check anyway:
            if not strategy:
                raise ValueError(f"Strategy with ID '{strategy_id}' does not exist or is empty.")

            # 4) Extract config from the strategy
            config: Dict[str, Any] = strategy.get('data', {})
            # For the new structure, we expect the user’s JSON to contain:
            #  - "trade_parameters" (dict)
            #  - "conditions" -> { "entry": [...], "exit": [...] }

            trade_parameters: Dict[str, Any] = config.get('trade_parameters', {})
            conditions: Dict[str, List[Dict[str, Any]]] = config.get('conditions', {})
            entry_conditions: List[Dict[str, Any]] = conditions.get('entry', [])
            exit_conditions: List[Dict[str, Any]] = conditions.get('exit', [])

            # 5) Check for missing components
            if not trade_parameters:
                raise ValueError(f"Strategy {strategy_id} is missing 'trade_parameters'.")
            if not entry_conditions:
                raise ValueError(f"Strategy {strategy_id} is missing 'conditions.entry'.")
            if not exit_conditions:
                raise ValueError(f"Strategy {strategy_id} is missing 'conditions.exit'.")

            # 6) Get budget (cash) for the strategy
            starting_cash = self.budget_manager.get_budget(strategy_id)
            if starting_cash is None:
                # Fallback if no budget was set
                starting_cash = 100000.0
            cerebro.broker.set_cash(starting_cash)

            # 7) Create and add the generated strategy
            bt_strategy = self._create_bt_strategy(trade_parameters, entry_conditions, exit_conditions)
            cerebro.addstrategy(bt_strategy)

            # 8) Log/print initial portfolio value
            initial_value = cerebro.broker.getvalue()
            self.logger.info(f"Starting Portfolio Value: {initial_value:.2f} USDT")
            print(f"Starting Portfolio Value: {initial_value:.2f} USDT")

            # 9) Run the backtest
            results = cerebro.run()

            # 10) Log/print final portfolio value
            final_value = cerebro.broker.getvalue()
            self.logger.info(f"Final Portfolio Value: {final_value:.2f} USDT")
            print(f"Final Portfolio Value: {final_value:.2f} USDT")

            # 11) Optionally plot results in ASCII
            self._plot_ascii_results(historical_data)

            # 12) Return results so the rest of your application can access them
            return {
                "initial_value": initial_value,
                "final_value": final_value,
                "results": results
            }

        except Exception as e:
            self.logger.error(f"Error during backtest: {e}", exc_info=True)
            raise

    def _plot_ascii_results(self, historical_data: pd.DataFrame):
        """
        Visualizes backtest results using ASCII.
        """
        try:
            closes = historical_data['close'].dropna().tolist()
            if not closes:
                raise ValueError("No close prices available for ASCII plotting.")

            ascii_chart = asciichartpy.plot(closes, {"height": 20, "format": "{:>8.2f}"})
            print("Backtest Results (ASCII Chart):")
            print(ascii_chart)

        except Exception as e:
            self.logger.error(f"Failed to generate ASCII plot: {e}", exc_info=True)
            raise

    def generate_synthetic_data(
        self,
        timeframe: str,
        duration_days: int,
        scenario: str = "neutral"
    ) -> pd.DataFrame:
        """
        Generates synthetic OHLCV data based on a given scenario.
        """
        try:
            # Convert timeframe like '1m' to '1min' if needed
            if timeframe.endswith('m'):
                timeframe = timeframe.replace('m', 'min')

            freq_per_day = pd.Timedelta("1D") / pd.Timedelta(timeframe)
            num_points = int(duration_days * freq_per_day)

            start_date = pd.Timestamp.now()
            data = {
                "timestamp": pd.date_range(start=start_date, periods=num_points, freq=timeframe),
                "open": [],
                "high": [],
                "low": [],
                "close": [],
                "volume": []
            }

            base_price = 100.0
            for _ in range(num_points):
                if scenario == "bullish":
                    # Slightly higher upward range
                    change = random.uniform(0, 2)
                elif scenario == "bearish":
                    # Slightly lower downward range
                    change = random.uniform(-2, 0)
                else:
                    # Neutral scenario
                    change = random.uniform(-1, 1)

                price = max(base_price + change, 1.0)  # Avoid going below 1
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
            self.logger.error(f"Failed to generate synthetic data: {e}", exc_info=True)
            raise

    def run_scenario_test(
        self,
        strategy_id: str,
        scenario: str,
        timeframe: str,
        duration_days: int
    ) -> Dict[str, Any]:
        """
        Runs a backtest with synthetic data based on a specific scenario.
        :returns: Dictionary with scenario test results, including final portfolio value.
        """
        try:
            # Load the strategy, ensuring it has the new structure
            strategy = self.strategy_manager.load_strategy(strategy_id)
            if not strategy:
                raise ValueError(f"Strategy with ID '{strategy_id}' does not exist or is empty.")

            # Generate synthetic data for the scenario
            synthetic_data = self.generate_synthetic_data(timeframe, duration_days, scenario)

            # Run backtest on the synthetic data
            result = self.run_backtest(strategy_id, synthetic_data)
            return result

        except Exception as e:
            self.logger.error(f"Error during scenario test: {e}", exc_info=True)
            raise
