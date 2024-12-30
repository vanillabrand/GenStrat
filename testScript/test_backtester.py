import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import logging
from backtester import Backtester
from strategy_manager import StrategyManager
from budget_manager import BudgetManager

# Usage : Unit Test : TestBacktester : python -m unittest test_backtester.py
class TestBacktester(unittest.TestCase):
    def setUp(self):
        """
        Set up the test environment with mocked dependencies.
        """
        self.mock_strategy_manager = MagicMock(spec=StrategyManager)
        self.mock_budget_manager = MagicMock(spec=BudgetManager)

        # Initialize the Backtester with mocked dependencies
        self.backtester = Backtester(
            strategy_manager=self.mock_strategy_manager,
            budget_manager=self.mock_budget_manager
        )
        self.backtester.logger = logging.getLogger("TestBacktester")

    def test_convert_dataframe_to_bt_feed_success(self):
        """
        Test the conversion of a valid DataFrame to Backtrader feed.
        """
        df = pd.DataFrame({
            "timestamp": ["2023-01-01 00:00:00", "2023-01-01 00:01:00"],
            "open": [100, 101],
            "high": [102, 103],
            "low": [99, 100],
            "close": [101, 102],
            "volume": [1000, 1200]
        })

        result = self.backtester._convert_dataframe_to_bt_feed(df)
        self.assertIsNotNone(result)

    def test_convert_dataframe_to_bt_feed_missing_columns(self):
        """
        Test the conversion of a DataFrame with missing columns.
        """
        df = pd.DataFrame({
            "timestamp": ["2023-01-01 00:00:00", "2023-01-01 00:01:00"],
            "open": [100, 101]
        })

        with self.assertRaises(ValueError):
            self.backtester._convert_dataframe_to_bt_feed(df)

    def test_create_bt_strategy(self):
        """
        Test dynamic creation of Backtrader strategy.
        """
        strategy_data = {
            "data": {
                "parameters": {"param1": 10},
                "entry_conditions": "self.data.close[0] > self.data.open[0]",
                "exit_conditions": "self.data.close[0] < self.data.open[0]",
                "risk_management": {"position_size": 1}
            }
        }

        bt_strategy = self.backtester._create_bt_strategy(strategy_data)
        self.assertTrue(issubclass(bt_strategy, type))

    def test_run_backtest_with_valid_data(self):
        """
        Test running a backtest with valid strategy and historical data.
        """
        strategy_id = "test-id"
        strategy_data = {
            "data": {
                "parameters": {"param1": 10},
                "entry_conditions": "self.data.close[0] > self.data.open[0]",
                "exit_conditions": "self.data.close[0] < self.data.open[0]",
                "risk_management": {"position_size": 1}
            }
        }

        self.mock_strategy_manager.load_strategy.return_value = strategy_data
        self.mock_budget_manager.get_budget.return_value = 100000

        historical_data = pd.DataFrame({
            "timestamp": ["2023-01-01 00:00:00", "2023-01-01 00:01:00"],
            "open": [100, 101],
            "high": [102, 103],
            "low": [99, 100],
            "close": [101, 102],
            "volume": [1000, 1200]
        })

        with patch("backtrader.Cerebro.run"), patch("backtrader.Cerebro.plot"):
            self.backtester.run_backtest(strategy_id, historical_data)

        self.mock_strategy_manager.load_strategy.assert_called_once_with(strategy_id)
        self.mock_budget_manager.get_budget.assert_called_once_with(strategy_id)

    def test_run_backtest_invalid_strategy(self):
        """
        Test running a backtest with an invalid strategy ID.
        """
        strategy_id = "invalid-id"
        self.mock_strategy_manager.load_strategy.side_effect = ValueError("Strategy not found.")

        with self.assertRaises(ValueError):
            self.backtester.run_backtest(strategy_id, pd.DataFrame())

    def test_generate_synthetic_data(self):
        """
        Test generating synthetic data.
        """
        scenario = "bullish"
        timeframe = "1m"
        duration_days = 30

        synthetic_data = self.backtester.generate_synthetic_data(scenario, timeframe, duration_days)
        self.assertIsInstance(synthetic_data, pd.DataFrame)
        self.assertIn("open", synthetic_data.columns)

    def test_run_scenario_test(self):
        """
        Test running a scenario test.
        """
        strategy_id = "test-id"
        scenario = "bearish"
        timeframe = "1m"
        duration_days = 30

        self.mock_strategy_manager.load_strategy.return_value = {
            "data": {
                "parameters": {"param1": 10},
                "entry_conditions": "self.data.close[0] > self.data.open[0]",
                "exit_conditions": "self.data.close[0] < self.data.open[0]",
                "risk_management": {"position_size": 1}
            }
        }

        with patch("backtrader.Cerebro.run"):
            self.backtester.run_scenario_test(strategy_id, scenario, timeframe, duration_days)

    def test_display_backtest_summary(self):
        """
        Test displaying backtest summary with valid data.
        """
        cerebro = MagicMock()
        cerebro.broker.getvalue.side_effect = [100000, 110000]

        with patch("asciichartpy.plot") as mock_plot:
            self.backtester.display_backtest_summary(cerebro)
            mock_plot.assert_called_once()

    def test_display_backtest_summary_empty_values(self):
        """
        Test displaying backtest summary when no values are present.
        """
        cerebro = MagicMock()
        cerebro.broker.getvalue.return_value = None

        with patch("asciichartpy.plot") as mock_plot:
            self.backtester.display_backtest_summary(cerebro)
            mock_plot.assert_not_called()

if __name__ == "__main__":
    unittest.main()
