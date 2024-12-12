import asyncio
import pandas as pd
import logging
import websockets
from finta import TA
import pandas_ta as pta
from typing import Dict, List


class MarketMonitor:
    """
    Monitors active trading strategies and evaluates market data in real time.
    Integrates with WebSocket APIs and calculates indicators to identify trade signals.
    """

    def __init__(self, exchange, strategy_manager, trade_executor):
        self.exchange = exchange
        self.strategy_manager = strategy_manager
        self.trade_executor = trade_executor
        self.logger = logging.getLogger(self.__class__.__name__)
        self.active_strategies = []
        self.indicators = {}
        self.websocket_cache = {}

    async def start_monitoring(self):
        """
        Continuously monitor active strategies and evaluate market data.
        """
        await self.exchange.load_markets()
        while True:
            try:
                self.active_strategies = self.strategy_manager.get_active_strategies()
                tasks = [self.monitor_strategy(strategy) for strategy in self.active_strategies]
                await asyncio.gather(*tasks)
            except Exception as e:
                self.logger.error(f"Error in start_monitoring: {e}")
            await asyncio.sleep(60)

    async def monitor_strategy(self, strategy):
        """
        Monitor a single strategy across its associated assets.
        """
        strategy_name = strategy['strategy_name']
        strategy_data = strategy['strategy_data']
        assets = strategy_data['assets']
        market_type = strategy_data.get('market_type', 'spot')

        for asset in assets:
            try:
                await self.analyze_market(asset, strategy_name, strategy_data, market_type)
            except Exception as e:
                self.logger.error(f"Error in monitoring strategy '{strategy_name}' for asset '{asset}': {e}")
                continue

    async def analyze_market(self, asset, strategy_name, strategy_data, market_type):
        """
        Analyze market data for a specific asset and evaluate trade conditions.
        """
        timeframe = self.get_shortest_timeframe(strategy_data)
        limit = 500

        # Fetch market data
        try:
            if asset not in self.websocket_cache:
                ohlcv = await self.exchange.fetch_ohlcv(
                    asset,
                    timeframe=timeframe,
                    limit=limit,
                    params={'type': market_type}
                )
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('datetime', inplace=True)
                self.websocket_cache[asset] = df
            else:
                df = self.websocket_cache[asset]
        except Exception as e:
            self.logger.error(f"Failed to fetch data for {asset}: {e}")
            return

        self.initialize_indicators(strategy_data, df)

        entry_signal = self.evaluate_conditions(strategy_data['conditions']['entry'])
        if entry_signal:
            await self.trade_executor.execute_trade(strategy_name, asset, 'buy', strategy_data, market_type)

        exit_signal = self.evaluate_conditions(strategy_data['conditions']['exit'])
        if exit_signal:
            await self.trade_executor.execute_trade(strategy_name, asset, 'sell', strategy_data, market_type)

    def initialize_indicators(self, strategy_data, df):
        """
        Initialize and cache indicators required for strategy conditions.
        """
        self.indicators = {}
        all_conditions = strategy_data['conditions']['entry'] + strategy_data['conditions']['exit']
        for condition in all_conditions:
            indicator_name = condition['indicator']
            indicator_params = condition.get('indicator_parameters', {})
            indicator_key = f"{indicator_name}_{indicator_params}"
            if indicator_key in self.indicators:
                continue
            try:
                if indicator_name.lower() == 'price':
                    self.indicators[indicator_key] = df['close']
                else:
                    indicator_series = self.get_indicator_series(indicator_name, df, indicator_params)
                    self.indicators[indicator_key] = indicator_series
            except ValueError as e:
                self.logger.error(e)
                raise
            except Exception as e:
                self.logger.error(f"Error initializing indicator '{indicator_name}': {e}")
                raise

    def get_indicator_series(self, indicator_name, df, indicator_params):
        """
        Calculate indicator series using either Finta or Pandas-TA.
        """
        try:
            indicator_name_upper = indicator_name.upper()
            indicator_function = getattr(TA, indicator_name_upper)
            indicator_series = indicator_function(df, **indicator_params)
            if isinstance(indicator_series, pd.DataFrame):
                indicator_series = indicator_series.iloc[:, 0]
            return indicator_series
        except AttributeError:
            pass
        except Exception as e:
            self.logger.error(f"Error calculating indicator '{indicator_name}' with Finta: {e}")
            pass
        try:
            indicator_name_lower = indicator_name.lower()
            indicator_function = getattr(pta, indicator_name_lower)
            params = {**indicator_params}
            indicator_series = indicator_function(close=df['close'], **params)
            if isinstance(indicator_series, pd.DataFrame):
                indicator_series = indicator_series.iloc[:, 0]
            return indicator_series
        except AttributeError:
            pass
        except Exception as e:
            self.logger.error(f"Error calculating indicator '{indicator_name}' with Pandas-TA: {e}")
            pass
        raise ValueError(f"Unsupported indicator: {indicator_name}")

    def evaluate_conditions(self, conditions):
        """
        Evaluate entry or exit conditions for a strategy.
        """
        for condition in conditions:
            indicator_name = condition['indicator']
            operator = condition['operator']
            value = condition['value']
            indicator_params = condition.get('indicator_parameters', {})
            indicator_key = f"{indicator_name}_{indicator_params}"
            indicator_series = self.indicators.get(indicator_key)
            if indicator_series is None or indicator_series.empty:
                self.logger.error(f"Indicator '{indicator_name}' not initialized or has no data.")
                return False
            indicator_value = indicator_series.iloc[-1]
            if isinstance(value, str):
                value_indicator_name = value
                value_indicator_params = condition.get('value_indicator_parameters', {})
                value_indicator_key = f"{value_indicator_name}_{value_indicator_params}"
                compare_series = self.indicators.get(value_indicator_key)
                if compare_series is None or compare_series.empty:
                    self.logger.error(f"Indicator '{value_indicator_name}' not initialized or has no data.")
                    return False
                compare_value = compare_series.iloc[-1]
            else:
                compare_value = float(value)
            if not self.evaluate_operator(indicator_value, operator, compare_value):
                return False
        return True

    def evaluate_operator(self, a, operator, b):
        """
        Evaluate a condition operator between two values.
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

    def get_shortest_timeframe(self, strategy_data):
        """
        Get the shortest timeframe from a strategy's conditions.
        """
        timeframes = []
        all_conditions = strategy_data['conditions']['entry'] + strategy_data['conditions']['exit']
        for condition in all_conditions:
            timeframes.append(condition.get('timeframe', '1d'))
        timeframe_minutes = [self.parse_timeframe(tf) for tf in timeframes]
        min_timeframe = min(timeframe_minutes)
        return self.format_timeframe(min_timeframe)

    def parse_timeframe(self, timeframe_str):
        """
        Parse a timeframe string into minutes.
        """
        unit = timeframe_str[-1]
        value = int(timeframe_str[:-1])
        if unit == 'm':
            return value
        elif unit == 'h':
            return value * 60
        elif unit == 'd':
            return value * 60 * 24
        else:
            self.logger.error(f"Unsupported timeframe unit: {unit}")
            raise ValueError(f"Unsupported timeframe unit: {unit}")

    def format_timeframe(self, minutes):
        """
        Format minutes into a timeframe string.
        """
        if minutes < 60:
            return f"{minutes}m"
        elif minutes < 1440:
            return f"{minutes // 60}h"
        else:
            return f"{minutes // 1440}d"
