import logging
import asyncio
from budget_manager import BudgetManager
from performance_manager import PerformanceManager
from risk_manager import RiskManager
from strategy_manager import StrategyManager

class TradeExecutor:
    """
    Handles the execution of trades based on strategies, budgets, and risk management rules.
    """

    def __init__(self, exchange, budget_manager: BudgetManager, performance_manager: PerformanceManager, risk_manager: RiskManager):
        self.exchange = exchange
        self.budget_manager = budget_manager
        self.performance_manager = performance_manager
        self.risk_manager = risk_manager
        self.logger = logging.getLogger(self.__class__.__name__)

    async def execute_trade(self, strategy_id: str, asset: str, side: str, trade_parameters: dict, risk_parameters: dict, market_type: str):
        """
        Executes a trade with given parameters and risk management.
        :param strategy_id: The ID of the strategy.
        :param asset: The trading pair (e.g., BTC/USDT).
        :param side: 'buy' or 'sell'.
        :param trade_parameters: Includes leverage, order type, and position size.
        :param risk_parameters: Includes stop loss, take profit, and trailing stop loss.
        :param market_type: Type of market (spot, futures, etc.).
        """
        try:
            # Check available budget
            budget = self.budget_manager.get_budget(strategy_id)
            if budget <= 0:
                self.logger.error(f"No budget available for strategy '{strategy_id}'.")
                return

            # Calculate position size
            ticker = await self.exchange.fetch_ticker(asset)
            price = ticker['last']
            amount = self._calculate_trade_amount(budget, price, trade_parameters.get('position_size', 1))

            # Execute trade
            order_type = trade_parameters.get('order_type', 'market')
            order = await self.exchange.create_order(
                symbol=asset,
                type=order_type,
                side=side,
                amount=amount,
                price=None if order_type == 'market' else price,
                params={'type': market_type}
            )

            self.logger.info(f"Executed {side} order for {amount} of {asset} at {price}")

            # Record trade in performance manager
            trade_data = {
                'strategy_id': strategy_id,
                'asset': asset,
                'side': side,
                'amount': amount,
                'entry_price': price,
                'order_id': order['id'],
                'timestamp': order['timestamp']
            }
            self.performance_manager.record_performance(strategy_id, trade_data)

            # Update budget
            self.budget_manager.update_budget(strategy_id, budget - (amount * price))

            # Apply risk management
            await self._apply_risk_management(asset, side, amount, price, risk_parameters, market_type)

        except Exception as e:
            self.logger.error(f"Failed to execute trade for strategy '{strategy_id}': {e}")

    async def _apply_risk_management(self, asset: str, side: str, amount: float, entry_price: float, risk_parameters: dict, market_type: str):
        """
        Sets up risk management orders (stop loss, take profit, trailing stop loss).
        :param asset: The trading pair.
        :param side: 'buy' or 'sell'.
        :param amount: Trade amount.
        :param entry_price: Entry price of the trade.
        :param risk_parameters: Risk management settings.
        :param market_type: Type of market (spot, futures, etc.).
        """
        try:
            orders = []
            if 'stop_loss' in risk_parameters:
                stop_price = entry_price * (1 - risk_parameters['stop_loss'] / 100) if side == 'buy' else entry_price * (1 + risk_parameters['stop_loss'] / 100)
                stop_order = await self.exchange.create_order(
                    symbol=asset,
                    type='stop',
                    side='sell' if side == 'buy' else 'buy',
                    amount=amount,
                    price=stop_price,
                    params={'type': market_type, 'stopPrice': stop_price}
                )
                orders.append(stop_order)

            if 'take_profit' in risk_parameters:
                tp_price = entry_price * (1 + risk_parameters['take_profit'] / 100) if side == 'buy' else entry_price * (1 - risk_parameters['take_profit'] / 100)
                tp_order = await self.exchange.create_order(
                    symbol=asset,
                    type='limit',
                    side='sell' if side == 'buy' else 'buy',
                    amount=amount,
                    price=tp_price,
                    params={'type': market_type}
                )
                orders.append(tp_order)

            for order in orders:
                self.logger.info(f"Risk management order placed: {order}")

        except Exception as e:
            self.logger.error(f"Failed to set risk management orders for {asset}: {e}")

    def _calculate_trade_amount(self, budget: float, price: float, position_size: float) -> float:
        """
        Calculates the trade amount based on the budget and price.
        :param budget: Available budget.
        :param price: Current price of the asset.
        :param position_size: Desired position size (percentage or absolute).
        :return: Calculated trade amount.
        """
        max_amount = budget / price
        return min(position_size, max_amount)
