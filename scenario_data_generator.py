import pandas as pd
import numpy as np
from datetime import datetime, timedelta

class ScenarioDataGenerator:
    
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
