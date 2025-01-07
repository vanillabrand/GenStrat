import logging
import asyncio

class TradeExecutor:
    """
    Executes trades based on strategy conditions, manages risk parameters, and dynamically monitors trades.
    """

    def __init__(self, exchange, trade_manager, budget_manager):
        self.exchange = exchange
        self.trade_manager = trade_manager
        self.budget_manager = budget_manager
        self.logger = logging.getLogger(self.__class__.__name__)

    async def execute_trade(self, strategy_name, asset, side, strategy_data, market_type="spot"):
        """
        Executes a trade dynamically based on JSON strategy parameters.
        :param strategy_name: Name of the strategy initiating the trade.
        :param asset: Asset to trade.
        :param side: 'buy' or 'sell'.
        :param strategy_data: JSON-based strategy parameters for the trade.
        :param market_type: Type of market (e.g., 'spot', 'futures').
        """
        try:
            # Check available budget
            budget = self.budget_manager.get_budget(strategy_name)
            if budget <= 0:
                self.logger.error(f"No available budget for strategy '{strategy_name}'.")
                return

            # Retrieve trade parameters
            trade_params = strategy_data.get("trade_parameters", {})
            position_size = trade_params.get("position_size", 1)
            risk_params = strategy_data.get("risk_management", {})
            stop_loss = risk_params.get("stop_loss")
            take_profit = risk_params.get("take_profit")
            trailing_stop = risk_params.get("trailing_stop")

            # Fetch current market price
            ticker = await self.exchange.fetch_ticker(asset)
            price = ticker["last"]

            # Calculate trade amount
            amount = self.calculate_amount(budget, price, position_size)

            # Execute the trade
            order_type = trade_params.get("order_type", "market")
            order = await self.exchange.create_order(
                symbol=asset,
                type=order_type,
                side=side,
                amount=amount,
                price=None if order_type == "market" else price,
                params={"type": market_type}
            )

            self.logger.info(f"{side.capitalize()} order executed for {amount} {asset} at {price}.")
            trade_record = {
                "strategy_name": strategy_name,
                "strategy_id": strategy_data["strategy_id"],
                "asset": asset,
                "side": side,
                "amount": amount,
                "price": price,
                "order_id": order["id"],
                "status": "open",
                "market_type": market_type,
                "timestamp": order["timestamp"],
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "trailing_stop": trailing_stop
            }

            # Record trade and update budget
            self.trade_manager.add_trade(trade_record)
            self.budget_manager.update_budget(strategy_name, budget - (amount * price))

            # Set risk management orders
            if stop_loss or take_profit or trailing_stop:
                await self.set_risk_management_orders(
                    asset, side, amount, price, stop_loss, take_profit, trailing_stop, market_type, strategy_name
                )
        except Exception as e:
            self.logger.error(f"Error executing trade for strategy '{strategy_name}': {e}")

    def calculate_amount(self, budget, price, position_size):
        """
        Calculates the trade amount based on available budget and position size.
        """
        try:
            max_amount = budget / price
            amount = min(position_size, max_amount)
            return amount
        except Exception as e:
            self.logger.error(f"Error calculating trade amount: {e}")
            raise

    async def set_risk_management_orders(self, asset, side, amount, entry_price, stop_loss, take_profit, trailing_stop, market_type, strategy_name):
        """
        Sets stop-loss, take-profit, and trailing stop orders for a trade.
        """
        try:
            orders = []
            if stop_loss:
                sl_price = entry_price * (1 - (stop_loss / 100)) if side == "buy" else entry_price * (1 + (stop_loss / 100))
                sl_order = await self.exchange.create_order(
                    symbol=asset,
                    type="stop",
                    side="sell" if side == "buy" else "buy",
                    amount=amount,
                    price=sl_price,
                    params={"stopPrice": sl_price, "type": market_type}
                )
                orders.append(sl_order)
                self.logger.info(f"Stop-loss set at {sl_price}.")

            if take_profit:
                tp_price = entry_price * (1 + (take_profit / 100)) if side == "buy" else entry_price * (1 - (take_profit / 100))
                tp_order = await self.exchange.create_order(
                    symbol=asset,
                    type="limit",
                    side="sell" if side == "buy" else "buy",
                    amount=amount,
                    price=tp_price,
                    params={"type": market_type}
                )
                orders.append(tp_order)
                self.logger.info(f"Take-profit set at {tp_price}.")

            if trailing_stop:
                ts_order = await self.exchange.create_order(
                    symbol=asset,
                    type="trailingStop",
                    side="sell" if side == "buy" else "buy",
                    amount=amount,
                    params={"type": market_type, "trailingStop": trailing_stop}
                )
                orders.append(ts_order)
                self.logger.info(f"Trailing stop set with callback rate {trailing_stop}%.")

            for order in orders:
                self.trade_manager.add_trade({
                    "strategy_name": strategy_name,
                    "asset": asset,
                    "side": order["side"],
                    "amount": amount,
                    "price": order.get("price", 0),
                    "order_id": order["id"],
                    "status": "open",
                    "market_type": market_type,
                    "timestamp": order.get("timestamp"),
                    "is_risk_management": True
                })
        except Exception as e:
            self.logger.error(f"Error setting risk management orders: {e}")

    async def fetch_price(self, asset):
        """
        Fetches the current price of the asset.
        """
        ticker = await self.exchange.fetch_ticker(asset)
        return ticker.get("last")

    async def close_trade(self, trade_id, reason):
        """
        Closes a trade based on specific conditions or reasons (e.g., stop-loss or take-profit).
        """
        trade = self.trade_manager.update_trade(trade_id, {"status": "closing"})
        if not trade:
            self.logger.warning(f"Trade {trade_id} not found for closure.")
            return
        try:
            side = "sell" if trade["side"] == "buy" else "buy"
            close_order = await self.exchange.create_order(
                symbol=trade["asset"],
                type="market",
                side=side,
                amount=trade["amount"],
                params={"type": trade["market_type"]}
            )
            trade.update({"status": "closed", "reason": reason, "close_order_id": close_order["id"]})
            self.logger.info(f"Trade {trade_id} closed: {close_order}")
        except Exception as e:
            self.logger.error(f"Failed to close trade {trade_id}: {e}")
