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
        Executes trades based on JSON strategy data with strict adherence to entry conditions.
        """
        try:
            budget = self.budget_manager.get_budget(strategy_name)
            if budget <= 0:
                self.logger.error(f"No budget for strategy '{strategy_name}'.")
                return

            # Extract parameters
            trade_params = strategy_data.get("trade_parameters", {})
            position_size = trade_params.get("position_size", 1)
            order_type = trade_params.get("order_type", "market")
            risk_params = strategy_data.get("risk_management", {})

            # Price and amount calculation
            ticker = await self.exchange.fetch_ticker(asset, params={"type": market_type})
            price = ticker["last"]
            amount = self.calculate_amount(budget, price, position_size)

            # Place trade
            order = await self.exchange.create_order(
                symbol=asset,
                type=order_type,
                side=side,
                amount=amount,
                price=None if order_type == "market" else price,
                params={"type": market_type}
            )

            self.logger.info(f"{side.capitalize()} trade for {amount} {asset} at {price}.")

            trade_record = {
                "strategy_name": strategy_name,
                "asset": asset,
                "side": side,
                "amount": amount,
                "price": price,
                "order_id": order["id"],
                "status": "open",
                "market_type": market_type,
                "timestamp": order["timestamp"],
            }

            # Record trade and deduct budget
            self.trade_manager.record_trade(trade_record)
            self.budget_manager.update_budget(strategy_name, budget - (amount * price))

        except Exception as e:
            self.logger.error(f"Trade execution error for strategy '{strategy_name}': {e}")

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

    async def get_current_market_data(self, assets):
        """
        Fetches current market data for multiple assets in a batch request.
        :param assets: List of asset symbols (e.g., ["BTC/USDT", "ETH/USDT"]).
        :return: Dictionary with asset symbols as keys and their market data as values.
        """
        try:
            # Use fetch_tickers to batch fetch market data
            market_data = await self.exchange.fetch_tickers(assets)
            return {
                symbol: {
                    "price": data["last"],
                    "high": data["high"],
                    "low": data["low"],
                    "volume": data["baseVolume"],
                    "change_24h": data.get("percentage", 0),
                }
                for symbol, data in market_data.items()
            }
        except Exception as e:
            self.logger.error(f"Error fetching market data for assets {assets}: {e}")
            return {}

    async def execute_trade(self, strategy_name, trade_details):
        """
        Executes a trade with balance validation.
        :param strategy_name: Name of the strategy initiating the trade.
        :param trade_details: Details of the trade to execute.
        """
        try:
            # Fetch wallet balance
            market_type = trade_details.get("market_type", "spot")
            wallet_balance = await self.fetch_wallet_balance(market_type)

            # Ensure sufficient balance for the trade
            asset = trade_details["asset"]
            required_amount = trade_details["amount"] * trade_details["price"]

            if asset not in wallet_balance or wallet_balance[asset] < required_amount:
                self.logger.warning(
                    f"Insufficient balance in {market_type} wallet for {asset}. "
                    f"Required: {required_amount:.2f}, Available: {wallet_balance.get(asset, 0):.2f}"
                )
                return

            # Proceed with trade execution
            order = await self.exchange.create_order(
                symbol=asset,
                type="market",
                side=trade_details["side"],
                amount=trade_details["amount"],
                price=None  # Market orders do not specify a price
            )

            # Record the trade
            self.trade_manager.record_trade({
                **trade_details,
                "strategy_name": strategy_name,
                "order_id": order["id"],
                "status": "open",
            })

            self.logger.info(f"Trade executed: {order}")
        except Exception as e:
            self.logger.error(f"Error executing trade: {e}")

    async def fetch_wallet_balance(self, market_type: str):
        """
        Fetches the wallet balance for the specified market type.
        :param market_type: The market type (e.g., 'spot', 'futures', 'margin').
        :return: A dictionary of available balances for each asset.
        """
        try:
            balance = await self.exchange.fetch_balance(params={"type": market_type})
            return balance["free"]  # 'free' represents available balance
        except Exception as e:
            self.logger.error(f"Error fetching wallet balance for {market_type}: {e}")
            return {}

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

