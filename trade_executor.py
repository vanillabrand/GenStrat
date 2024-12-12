import logging
import asyncio


class TradeExecutor:
    """
    Executes trades and manages associated risk using stop loss, take profit, and trailing stop orders.
    """

    def __init__(self, exchange, budget_manager, risk_manager, trade_manager):
        self.exchange = exchange
        self.budget_manager = budget_manager
        self.risk_manager = risk_manager
        self.trade_manager = trade_manager
        self.logger = logging.getLogger(self.__class__.__name__)

    async def execute_trade(self, strategy_name, asset, side, strategy_data, market_type):
        """
        Execute a trade and set up risk management orders if applicable.
        """
        try:
            budget = self.budget_manager.get_budget(strategy_name)
            if budget <= 0:
                self.logger.error(f"No budget available for strategy '{strategy_name}'.")
                return

            position_size = strategy_data['trade_parameters'].get('position_size', 1)
            risk_params = strategy_data.get('risk_management', {})
            stop_loss = risk_params.get('stop_loss')
            take_profit = risk_params.get('take_profit')
            trailing_stop = risk_params.get('trailing_stop_loss')

            ticker = await self.exchange.fetch_ticker(asset, params={'type': market_type})
            price = ticker['last']

            amount = self.calculate_amount(budget, price, position_size)
            order_type = strategy_data['trade_parameters'].get('order_type', 'market')

            order = await self.exchange.create_order(
                symbol=asset,
                type=order_type,
                side=side,
                amount=amount,
                price=None if order_type == 'market' else price,
                params={'type': market_type}
            )

            self.logger.info(f"Executed {side} order for {amount} of {asset} at {price}")
            trade_record = {
                'strategy_name': strategy_name,
                'asset': asset,
                'side': side,
                'amount': amount,
                'price': price,
                'order_id': order['id'],
                'status': 'open',
                'market_type': market_type,
                'timestamp': order['timestamp'],
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'trailing_stop': trailing_stop
            }

            self.trade_manager.record_trade(trade_record)
            self.budget_manager.update_budget(strategy_name, budget - (amount * price))

            if stop_loss or take_profit or trailing_stop:
                await self.set_risk_management_orders(asset, side, amount, price, stop_loss, take_profit, trailing_stop, market_type)

        except Exception as e:
            self.logger.error(f"Error executing trade for strategy '{strategy_name}': {e}")

    def calculate_amount(self, budget, price, position_size):
        """
        Calculate the amount of the asset to trade based on budget and position size.
        """
        max_amount = budget / price
        amount = min(position_size, max_amount)
        return amount

    async def set_risk_management_orders(self, asset, side, amount, entry_price, stop_loss, take_profit, trailing_stop, market_type):
        """
        Place stop loss, take profit, and trailing stop orders.
        """
        try:
            orders = []
            if stop_loss:
                sl_price = entry_price * (1 - (stop_loss / 100)) if side == 'buy' else entry_price * (1 + (stop_loss / 100))
                sl_order = await self.exchange.create_order(
                    symbol=asset,
                    type='stop',
                    side='sell' if side == 'buy' else 'buy',
                    amount=amount,
                    price=sl_price,
                    params={'stopPrice': sl_price, 'type': market_type}
                )
                orders.append(sl_order)
                self.logger.info(f"Set stop loss at {sl_price}")

            if take_profit:
                tp_price = entry_price * (1 + (take_profit / 100)) if side == 'buy' else entry_price * (1 - (take_profit / 100))
                tp_order = await self.exchange.create_order(
                    symbol=asset,
                    type='limit',
                    side='sell' if side == 'buy' else 'buy',
                    amount=amount,
                    price=tp_price,
                    params={'type': market_type}
                )
                orders.append(tp_order)
                self.logger.info(f"Set take profit at {tp_price}")

            if trailing_stop:
                ts_order = await self.exchange.create_order(
                    symbol=asset,
                    type='trailingStop',
                    side='sell' if side == 'buy' else 'buy',
                    amount=amount,
                    params={
                        'type': market_type,
                        'trailingStop': trailing_stop
                    }
                )
                orders.append(ts_order)
                self.logger.info(f"Set trailing stop loss with callback rate {trailing_stop}%")

            for order in orders:
                self.trade_manager.record_trade({
                    'strategy_name': "Risk Management",
                    'asset': asset,
                    'side': order['side'],
                    'amount': amount,
                    'price': order.get('price', None),
                    'order_id': order['id'],
                    'status': 'open',
                    'market_type': market_type,
                    'timestamp': order['timestamp'],
                    'is_risk_management': True
                })

        except Exception as e:
            self.logger.error(f"Error setting risk management orders: {e}")
