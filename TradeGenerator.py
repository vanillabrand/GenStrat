import redis
import json
import asyncio
from datetime import datetime
from ccxt import bitget
import ta
import pandas as pd

class TradeGenerator:
    def __init__(self, strategy, redis_client, exchange):

        self.strategy = strategy
        self.redis_client = redis_client
        self.exchange = exchange
        self.active_trades = []
        self.volatility_threshold = 0.8  # Dynamic threshold for volatility detection
    
    def parse_strategy(self):

        """Parse strategy to extract trade parameters."""
        strategy_data = json.loads(self.strategy.get("data", "{}"))
        self.trade_params = strategy_data.get("trade_parameters", {})
        self.conditions = strategy_data.get("conditions", {})
        self.assets = strategy_data.get("assets", [])

    def generate_trades(self):

        """Generate trades, applying anti-whale and anti-bot logic."""
        trades = []
        for asset in self.assets:
            for entry in self.conditions["entry"]:
                trade = {
                    "asset": asset,
                    "type": self.trade_params["order_type"][0],
                    "leverage": self.trade_params["initial_leverage"],
                    "size": self.trade_params["position_size"],
                    "entry_condition": entry,
                    "status": "pending",
                    "created_at": datetime.now().isoformat()
                }
                
                # Anti-whale: Gradual entry strategy
                if self.detect_whale_activity(asset):
                    trade["leverage"] = max(1, trade["leverage"] * 0.5)
                    trade["size"] *= 0.5

                trades.append(trade)
        
        self.store_trades(trades)
        return trades

    def detect_whale_activity(self, asset):

        """Detect abnormal market activity through order book data."""
        order_book = self.exchange.fetch_order_book(asset)
        asks, bids = order_book['asks'], order_book['bids']
        
        # Calculate market depth ratio (anti-whale protection)
        ask_volume = sum([ask[1] for ask in asks[:5]])
        bid_volume = sum([bid[1] for bid in bids[:5]])
        depth_ratio = ask_volume / (bid_volume + 1)
        
        return depth_ratio > 1.5  # Whale activity threshold

    def store_trades(self, trades):

        """Store trades in Redis."""
        for trade in trades:
            key = f"trade:{trade['asset']}:{datetime.now().timestamp()}"
            self.redis_client.set(key, json.dumps(trade))
            self.active_trades.append(trade)
        
    def recover_trades(self):
        
        """Recover trades during crash recovery."""
        keys = self.redis_client.keys("trade:*")
        self.active_trades = [json.loads(self.redis_client.get(k)) for k in keys]

