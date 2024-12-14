import pandas as pd
import logging

class Backtester:
    """
    Provides functionality for backtesting trading strategies using historical data.
    """

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    def run_backtest(self, strategy, historical_data):
        """
        Runs a backtest for a given strategy on historical data.

        :param strategy: The strategy JSON containing conditions, trade parameters, and risk management.
        :param historical_data: A Pandas DataFrame containing historical OHLCV data.
        """
        try:
            self.logger.info("Starting backtest...")
            results = self.simulate_trades(strategy, historical_data)
            self.display_results(results)
        except Exception as e:
            self.logger.error(f"Backtest failed: {e}")
            raise

    def simulate_trades(self, strategy, historical_data):
        """
        Simulates trades based on the strategy and historical data.

        :param strategy: The strategy JSON.
        :param historical_data: A Pandas DataFrame containing historical OHLCV data.
        :return: A dictionary containing backtest results.
        """
        conditions = strategy['conditions']
        entry_conditions = conditions['entry']
        exit_conditions = conditions['exit']

        # Initialize backtest metrics
        balance = 10000  # Starting balance in USD
        position = 0  # Current position size in asset units
        equity_curve = []  # Track equity over time

        # Process historical data
        for index, row in historical_data.iterrows():
            price = row['close']

            # Check entry conditions
            if self.evaluate_conditions(entry_conditions, row):
                position_size = balance / price
                position += position_size
                balance -= position_size * price
                self.logger.info(f"Entered position at {price}, size: {position_size}")

            # Check exit conditions
            if self.evaluate_conditions(exit_conditions, row) and position > 0:
                balance += position * price
                self.logger.info(f"Exited position at {price}, size: {position}")
                position = 0

            # Update equity
            equity = balance + (position * price)
            equity_curve.append(equity)

        # Finalize metrics
        pnl = balance - 10000  # Profit or Loss
        roi = (pnl / 10000) * 100  # Return on Investment

        return {
            'final_balance': balance,
            'pnl': pnl,
            'roi': roi,
            'equity_curve': equity_curve
        }

    def evaluate_conditions(self, conditions, row):
        """
        Evaluates a set of conditions on a given row of data.

        :param conditions: A list of conditions to evaluate.
        :param row: A Pandas Series representing a row of historical data.
        :return: True if all conditions are met, False otherwise.
        """
        for condition in conditions:
            indicator = condition['indicator']
            operator = condition['operator']
            value = condition['value']

            # Get the indicator value from the row
            indicator_value = row.get(indicator)
            if indicator_value is None:
                self.logger.error(f"Missing indicator '{indicator}' in data.")
                return False

            # Evaluate the condition
            if not self.compare(indicator_value, operator, value):
                return False

        return True

    def compare(self, a, operator, b):
        """
        Compares two values based on an operator.

        :param a: The first value.
        :param operator: The comparison operator (>, <, >=, <=, ==).
        :param b: The second value.
        :return: The result of the comparison.
        """
        if operator == '>':
            return a > b
        elif operator == '<':
            return a < b
        elif operator == '==':
            return a == b
        elif operator == '>=':
            return a >= b
        elif operator == '<=':
            return a <= b
        else:
            self.logger.error(f"Unsupported operator: {operator}")
            raise ValueError(f"Unsupported operator: {operator}")

    def display_results(self, results):
        """
        Displays the results of the backtest.

        :param results: A dictionary containing backtest results.
        """
        print("\n--- Backtest Results ---")
        print(f"Final Balance: ${results['final_balance']:.2f}")
        print(f"PnL: ${results['pnl']:.2f}")
        print(f"ROI: {results['roi']:.2f}%")
        print("Equity Curve:")
        print(results['equity_curve'])
