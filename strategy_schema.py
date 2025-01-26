from typing import Dict, List, Optional, Union
from dataclasses import dataclass
import json

@dataclass
class RiskManagement:
    stop_loss: float
    take_profit: float
    max_drawdown: Optional[float] = None
    position_size: Optional[float] = None

@dataclass
class TradeParameters:
    leverage: int
    order_type: str
    time_frame: str
    position_type: str
    entry_price: Optional[float] = None
    order_size: Optional[float] = None

@dataclass
class Strategy:
    id: str
    title: str
    description: str
    strategy_name: str
    market_type: str
    assets: List[str]
    trade_parameters: TradeParameters
    conditions: Dict[str, Union[str, float, int]]
    risk_management: RiskManagement
    active: bool = False
    trades: List[Dict] = None

class StrategyFormatter:
    @staticmethod
    def to_redis_format(strategy: Strategy) -> Dict:
        """Convert Strategy object to Redis-compatible format"""
        return {
            "id": strategy.id,
            "title": strategy.title,
            "description": strategy.description,
            "data": json.dumps({
                "strategy_name": strategy.strategy_name,
                "market_type": strategy.market_type,
                "assets": strategy.assets,
                "trade_parameters": vars(strategy.trade_parameters),
                "conditions": strategy.conditions,
                "risk_management": vars(strategy.risk_management)
            }),
            "active": str(strategy.active),
            "trades": json.dumps(strategy.trades or [])
        }

    @staticmethod
    def from_redis_format(redis_data: Dict) -> Strategy:
        """Convert Redis data back to Strategy object"""
        data = json.loads(redis_data["data"])
        
        trade_params = TradeParameters(
            leverage=data["trade_parameters"]["leverage"],
            order_type=data["trade_parameters"]["order_type"],
            time_frame=data["trade_parameters"]["time_frame"],
            position_type=data["trade_parameters"]["position_type"],
            entry_price=data["trade_parameters"].get("entry_price"),
            order_size=data["trade_parameters"].get("order_size")
        )
        
        risk_mgmt = RiskManagement(
            stop_loss=data["risk_management"]["stop_loss"],
            take_profit=data["risk_management"]["take_profit"],
            max_drawdown=data["risk_management"].get("max_drawdown"),
            position_size=data["risk_management"].get("position_size")
        )

        return Strategy(
            id=redis_data["id"],
            title=redis_data["title"],
            description=redis_data["description"],
            strategy_name=data["strategy_name"],
            market_type=data["market_type"],
            assets=data["assets"],
            trade_parameters=trade_params,
            conditions=data["conditions"],
            risk_management=risk_mgmt,
            active=redis_data["active"] == "True",
            trades=json.loads(redis_data["trades"])
        )
