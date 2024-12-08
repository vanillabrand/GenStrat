# backtester.py

import backtrader as bt
import pandas as pd
import logging
from monitor import Monitor
import importlib

class Backtester:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)
        
        # Console handler for logging
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        
        # Formatter for the logs
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        
        # Avoid adding multiple handlers if already present
        if not self.logger.handlers:
            self.logger.addHandler(ch)
        
        # Initialize the Monitor
        self.monitor = Monitor()
    
    def run_backtest(self, strategy_data: dict, historical_data: pd.DataFrame):
        """
        Executes the backtest using Backtrader.
        
        Args:
            strategy_data (dict): Dictionary containing strategy configuration.
            historical_data (pd.DataFrame): DataFrame containing historical OHLCV data.
        """
        cerebro = bt.Cerebro()
        
        # Add data to Cerebro
        data_feed = bt.feeds.PandasData(dataname=historical_data)
        cerebro.adddata(data_feed)
        
        # Create and add the custom strategy
        strategy_class = self.create_strategy_class(strategy_data, self.monitor)
        cerebro.addstrategy(strategy_class)
        
        # Set initial capital
        cerebro.broker.setcash(100000.0)
        
        # Add analyzers for performance metrics
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe_ratio')
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
        
        self.logger.info("Starting backtest...")
        results = cerebro.run()
        self.logger.info("Backtest completed.")
        
        # Retrieve the first strategy instance
        strat = results[0]
        
        # Extract analyzer data
        sharpe_ratio = strat.analyzers.sharpe_ratio.get_analysis().get('sharperatio', 'N/A')
        max_drawdown = strat.analyzers.drawdown.get_analysis().get('max', 'N/A')
        total_return = strat.analyzers.returns.get_analysis().get('rtot', 0) * 100  # Convert to percentage
        
        # Log performance metrics
        self.logger.info(f"Sharpe Ratio: {sharpe_ratio}")
        self.logger.info(f"Max Drawdown: {max_drawdown}%")
        self.logger.info(f"Total Return: {total_return:.2f}%")
        
        # Log final portfolio value
        final_value = cerebro.broker.getvalue()
        self.logger.info(f"Final Portfolio Value: {final_value:.2f}")
        
        # Display all executed trades
        self.display_trades()
        
        # Export trades to CSV
        self.monitor.export_trades_to_csv('trade_log.csv')
        
        # Optionally plot the result
        # cerebro.plot(style='candlestick')
    
    def create_strategy_class(self, strategy_data: dict, monitor: Monitor):
        """
        Dynamically creates a CustomStrategy class based on strategy_data and integrates with the monitor.
        
        Args:
            strategy_data (dict): Dictionary containing strategy configuration.
            monitor (Monitor): Instance of the Monitor class to track trades.
        
        Returns:
            CustomStrategy: A dynamically created strategy class.
        """
        class CustomStrategy(bt.Strategy):
            params = (
                ('strategy_data', strategy_data),
                ('monitor', monitor),
            )

            def __init__(self):
                self.monitor = self.params.monitor
                self.strategy_data = self.params.strategy_data
                self.indicators = {}
                
                # Initialize indicators based on strategy_data
                for condition in self.strategy_data.get('conditions', {}).get('entry', []):
                    indicator_name = condition['indicator']
                    indicator_params = condition.get('indicator_parameters', {})
                    self.add_indicator(indicator_name, indicator_params)
                
                for condition in self.strategy_data.get('conditions', {}).get('exit', []):
                    indicator_name = condition['indicator']
                    indicator_params = condition.get('indicator_parameters', {})
                    self.add_indicator(indicator_name, indicator_params)
                
                # To prevent multiple orders
                self.order = None

            def add_indicator(self, indicator_name: str, params: dict):
                """
                Dynamically adds an indicator to the strategy.
                
                Args:
                    indicator_name (str): Name of the indicator.
                    params (dict): Parameters for the indicator.
                """
                if indicator_name in self.indicators:
                    return  # Indicator already added
                
                try:
                    # Attempt to get the indicator class from backtrader.indicators
                    indicator_class = getattr(bt.indicators, indicator_name)
                except AttributeError:
                    # Attempt to load from backtrader.indicators.external or other modules if necessary
                    try:
                        indicator_module = importlib.import_module('backtrader.indicators.' + indicator_name)
                        indicator_class = getattr(indicator_module, indicator_name)
                    except (ImportError, AttributeError):
                        self.monitor.logger.error(f"Indicator '{indicator_name}' not found in Backtrader.")
                        raise ValueError(f"Unsupported indicator: {indicator_name}")
                
                # Initialize the indicator with provided parameters
                try:
                    self.indicators[indicator_name] = indicator_class(self.data.close, **params)
                except TypeError as e:
                    self.monitor.logger.error(f"Error initializing indicator '{indicator_name}': {e}")
                    raise ValueError(f"Invalid parameters for indicator '{indicator_name}': {e}")

            def next(self):
                if self.order:
                    return  # Wait until the order is processed

                # Check if we are in the market
                if not self.position:
                    # Check entry conditions
                    entry_signal = True
                    for condition in self.strategy_data.get('conditions', {}).get('entry', []):
                        indicator_name = condition['indicator']
                        operator = condition['operator']
                        value = condition['value']
                        indicator = self.indicators.get(indicator_name)
                        if not indicator:
                            self.monitor.logger.error(f"Indicator '{indicator_name}' not initialized.")
                            entry_signal = False
                            break
                        indicator_value = indicator[0]
                        if isinstance(value, str) and value in self.indicators:
                            compare_value = self.indicators[value][0]
                        else:
                            try:
                                compare_value = float(value)
                            except ValueError:
                                self.monitor.logger.error(f"Invalid comparison value: {value}")
                                entry_signal = False
                                break
                        if not self.evaluate_operator(indicator_value, operator, compare_value):
                            entry_signal = False
                            break
                    if entry_signal:
                        self.logger.info(f"Entry signal detected: Buying at {self.data.close[0]:.2f}")
                        self.order = self.buy()
                        # Log trade entry
                        self.monitor.log_trade({
                            'action': 'buy',
                            'price': self.data.close[0],
                            'datetime': self.data.datetime.datetime(0).strftime("%Y-%m-%d %H:%M:%S")
                        })
                else:
                    # Check exit conditions
                    exit_signal = False
                    for condition in self.strategy_data.get('conditions', {}).get('exit', []):
                        indicator_name = condition['indicator']
                        operator = condition['operator']
                        value = condition['value']
                        indicator = self.indicators.get(indicator_name)
                        if not indicator:
                            self.monitor.logger.error(f"Indicator '{indicator_name}' not initialized.")
                            continue
                        indicator_value = indicator[0]
                        if isinstance(value, str) and value in self.indicators:
                            compare_value = self.indicators[value][0]
                        else:
                            try:
                                compare_value = float(value)
                            except ValueError:
                                self.monitor.logger.error(f"Invalid comparison value: {value}")
                                continue
                        if self.evaluate_operator(indicator_value, operator, compare_value):
                            exit_signal = True
                            break
                    if exit_signal:
                        self.logger.info(f"Exit signal detected: Selling at {self.data.close[0]:.2f}")
                        self.order = self.sell()
                        # Log trade exit
                        self.monitor.log_trade({
                            'action': 'sell',
                            'price': self.data.close[0],
                            'datetime': self.data.datetime.datetime(0).strftime("%Y-%m-%d %H:%M:%S")
                        })

            def notify_order(self, order):
                if order.status in [order.Submitted, order.Accepted]:
                    # Order is submitted/accepted, no action needed
                    return

                if order.status in [order.Completed]:
                    if order.isbuy():
                        self.logger.info(f"BUY EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm {order.executed.comm:.2f}")
                    elif order.issell():
                        self.logger.info(f"SELL EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm {order.executed.comm:.2f}")
                    
                    self.order = None  # Reset order

                elif order.status in [order.Canceled, order.Margin, order.Rejected]:
                    self.logger.warning("Order Canceled/Margin/Rejected")
                    self.order = None  # Reset order

            @staticmethod
            def evaluate_operator(a, operator, b):
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
                    raise ValueError(f"Unsupported operator: {operator}")

        return CustomStrategy

    def display_trades(self):
        """
        Displays the logged trades in a table format.
        """
        trades = self.monitor.get_trades()
        if not trades:
            self.logger.info("No trades were executed during the backtest.")
            return

        # Create a table using PrettyTable
        from prettytable import PrettyTable

        table = PrettyTable()
        table.field_names = ["Action", "Price", "Datetime"]
        for trade in trades:
            table.add_row([trade['action'].capitalize(), f"{trade['price']:.2f}", trade['datetime']])

        self.logger.info(f"\n{table}")
