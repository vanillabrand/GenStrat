import logging
import asyncio


class TradeExecutor:
    """
    Executes trades based on strategy conditions, manages risk parameters, and dynamically monitors trades.
    Handles partial fills and fallback to market orders if needed.
    """

    def __init__(self, exchange, trade_manager, budget_manager):
        self.exchange = exchange
        self.trade_manager = trade_manager
        self.budget_manager = budget_manager
        self.logger = logging.getLogger(self.__class__.__name__)
        self.order_timeout = 60  # Timeout in seconds for limit orders before retrying as market order

    async def execute_trade(self, strategy_name, asset, side, strategy_data, market_type="spot"):
        """
        Executes a trade dynamically based on JSON strategy parameters.
        """
        try:
            budget = self.budget_manager.get_budget(strategy_name)
            if budget <= 0:
                self.logger.warning(f"No available budget for strategy '{strategy_name}'. Trade skipped.")
                return

            trade_params = strategy_data.get("trade_parameters", {})
            position_size = trade_params.get("position_size", 1)
            risk_params = strategy_data.get("risk_management", {})

            stop_loss = risk_params.get("stop_loss")
            take_profit = risk_params.get("take_profit")
            trailing_stop = risk_params.get("trailing_stop")

            ticker = await self.exchange.fetch_ticker(asset)
            price = ticker["last"]

            amount = self.calculate_amount(budget, price, position_size)

            if amount <= 0:
                self.logger.warning(f"Insufficient budget to place trade for {asset}.")
                return

            order_type = trade_params.get("order_type", "limit")
            order = await self.exchange.create_order(
                symbol=asset,
                type=order_type,
                side=side,
                amount=amount,
                price=None if order_type == "market" else price,
                params={"type": market_type}
            )

            self.logger.info(f"{side.capitalize()} order placed: {amount} {asset} at {price}. Waiting for fill...")

            # Monitor the order for fills
            await self.monitor_order_fill(order, strategy_name, asset, side, amount, price, market_type)

        except Exception as e:
            self.logger.error(f"Error executing trade for strategy '{strategy_name}': {e}")
            self.trade_manager.add_failed_trade(strategy_name, asset, side, strategy_data)

    async def monitor_order_fill(self, order, strategy_name, asset, side, amount, price, market_type):
        """
        Monitors the status of an order to detect partial fills and fallback to market order if necessary.
        """
        order_id = order["id"]
        start_time = asyncio.get_event_loop().time()

        while True:
            await asyncio.sleep(5)
            order_status = await self.exchange.fetch_order(order_id, asset)

            filled = order_status.get("filled", 0)
            remaining = order_status.get("remaining", 0)

            if order_status["status"] == "closed":
                self.logger.info(f"Order {order_id} for {asset} fully filled.")
                break
            elif filled > 0 and remaining > 0:
                self.logger.info(f"Order {order_id} partially filled. Remaining: {remaining} {asset}")
                await self.handle_partial_fill(order_status, strategy_name, asset, side, remaining, market_type)
                break
            elif asyncio.get_event_loop().time() - start_time > self.order_timeout:
                self.logger.warning(f"Order {order_id} not filled within timeout. Fallback to market order.")
                await self.fallback_to_market(order_id, asset, side, remaining, market_type)
                break

    async def handle_partial_fill(self, order_status, strategy_name, asset, side, remaining, market_type):
        """
        Handles partially filled trades by retrying the remaining amount as a new order.
        Updates the budget with the unspent portion.
        """
        price = order_status.get("price", 0)

        # Calculate the unused portion of the budget and reallocate
        unused_budget = remaining * price
        current_budget = self.budget_manager.get_budget(strategy_name)
        updated_budget = current_budget + unused_budget

        # Ensure budget is not exceeding the available exchange balance
        exchange_balance = await self.fetch_asset_balance(asset)
        if updated_budget > exchange_balance:
            updated_budget = exchange_balance
            self.logger.warning(
                f"Budget for {strategy_name} capped at {updated_budget:.2f} USDT due to limited exchange balance."
            )

        self.budget_manager.update_budget(strategy_name, updated_budget)
        self.logger.info(f"Returned {unused_budget:.2f} USDT to budget for strategy '{strategy_name}'.")

        retry_trade = {
            "strategy_name": strategy_name,
            "asset": asset,
            "side": side,
            "trade_parameters": {"position_size": remaining, "order_type": "market"},
            "strategy_id": order_status.get("strategy_id"),
            "risk_management": {}
        }

        self.trade_manager.add_failed_trade(strategy_name, asset, side, retry_trade)
        self.logger.info(f"Requeued remaining {remaining} {asset} for trade execution.")

    async def fallback_to_market(self, order_id, asset, side, remaining, market_type):
        """
        Cancels the limit order and executes the remaining amount as a market order.
        """
        await self.exchange.cancel_order(order_id, asset)
        self.logger.info(f"Cancelled limit order {order_id}. Executing remaining amount as market order.")

        market_order = await self.exchange.create_order(
            symbol=asset,
            type="market",
            side=side,
            amount=remaining,
            params={"type": market_type}
        )
        self.logger.info(f"Market order executed for remaining {remaining} {asset}. Order ID: {market_order['id']}")

    async def fetch_asset_balance(self, asset):
        balances = await self.exchange.fetch_balance()
        return balances.get(asset, {}).get('free', 0)

    def calculate_amount(self, budget, price, position_size):
        try:
            max_amount = budget / price
            return min(position_size, max_amount)
        except Exception as e:
            self.logger.error(f"Error calculating trade amount: {e}")
            return 0
        
    async def close_trade(self, trade_id, reason, graceful_exit=True):
        """
        Closes a trade based on specific conditions. Performs a graceful exit if enabled, 
        otherwise executes an immediate market close.
        :param trade_id: The ID of the trade to close.
        :param reason: Reason for trade closure (e.g., stop-loss, strategy deactivation).
        :param graceful_exit: If True, waits for favorable conditions to exit the trade.
        """
        trade = self.trade_manager.get_trade_by_id(trade_id)
        if not trade:
            self.logger.warning(f"Trade {trade_id} not found for closure.")
            return

        try:
            side = "sell" if trade["side"] == "buy" else "buy"
            asset = trade["asset"]
            amount = trade["amount"]

            if graceful_exit:
                self.logger.info(f"Initiating graceful exit for trade {trade_id}. Monitoring for optimal exit...")
                await self.monitor_trade_exit(trade_id, asset, side, trade)
            else:
                self.logger.info(f"Closing trade {trade_id} immediately via market order.")
                close_order = await self.exchange.create_order(
                    symbol=asset,
                    type="market",
                    side=side,
                    amount=amount,
                    params={"type": trade["market_type"]}
                )
                self.logger.info(f"Trade {trade_id} closed: {close_order}. Reason: {reason}")
                trade.update({"status": "closed", "reason": reason, "close_order_id": close_order["id"]})
                self.trade_manager.transition_to_closed(trade_id)
                self.budget_manager.return_budget(trade["strategy_name"], close_order["cost"])
        except Exception as e:
            self.logger.error(f"Failed to close trade {trade_id}: {e}")

    async def monitor_trade_exit(self, trade_id, asset, side, trade):
        """
        Monitors a trade until optimal exit conditions are met.
        :param trade_id: Trade ID to monitor.
        :param asset: Asset being traded.
        :param side: Trade direction ('buy' or 'sell').
        :param trade: Trade details dictionary.
        """
        stop_loss = trade.get("stop_loss")
        take_profit = trade.get("take_profit")

        while True:
            try:
                ticker = await self.exchange.fetch_ticker(asset)
                current_price = ticker["last"]

                # Check exit conditions
                if (side == "buy" and (current_price <= stop_loss or current_price >= take_profit)) or \
                (side == "sell" and (current_price >= stop_loss or current_price <= take_profit)):

                    self.logger.info(f"Exit conditions met for trade {trade_id}. Closing trade.")
                    await self.close_trade(trade_id, "graceful_exit", graceful_exit=False)
                    break

                self.logger.info(f"Trade {trade_id} still within bounds. Monitoring continues.")
            except Exception as e:
                self.logger.error(f"Error monitoring exit for trade {trade_id}: {e}")

            await asyncio.sleep(10)  # Check every 10 seconds

