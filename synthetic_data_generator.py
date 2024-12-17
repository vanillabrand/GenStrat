import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def generate_synthetic_data(timeframe: str = "1m", points: int = 1000) -> pd.DataFrame:
    """
    Generates synthetic OHLCV data for backtesting.

    :param timeframe: Timeframe for synthetic data (e.g., '1m', '5m', '1h', '1d').
    :param points: Number of data points to generate.
    :return: A pandas DataFrame containing OHLCV data.
    """
    # Map timeframe to minutes
    timeframe_map = {
        "1m": 1,
        "5m": 5,
        "10m": 10,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "2h": 120,
        "4h": 240,
        "8h": 480,
        "1d": 1440,
        "1w": 10080,
        "1M": 43200  # Approximation for 30 days
    }

    if timeframe not in timeframe_map:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    interval_minutes = timeframe_map[timeframe]
    start_time = datetime.now() - timedelta(minutes=interval_minutes * points)

    # Generate synthetic data
    timestamps = [start_time + timedelta(minutes=interval_minutes * i) for i in range(points)]
    prices = np.cumsum(np.random.normal(0, 1, points)) + 100  # Random walk around 100
    high = prices + np.random.uniform(0.5, 2.0, points)
    low = prices - np.random.uniform(0.5, 2.0, points)
    open_ = prices + np.random.uniform(-1, 1, points)
    close = prices + np.random.uniform(-1, 1, points)
    volume = np.random.randint(1, 1000, points)

    # Create DataFrame
    synthetic_data = pd.DataFrame({
        "timestamp": [int(ts.timestamp() * 1000) for ts in timestamps],
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume
    })

    return synthetic_data
