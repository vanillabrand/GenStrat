import logging
import asyncio
from asyncio_throttle import Throttler


class TradeExecutor:
    """
    Executes trades based on strategy conditions, manages risk parameters, and dynamically monitors trades.
    Handles partial fills, fallback to market orders, and optimal exit conditions.
    """

    def __init__(self, exchange, trade_manager, budget_manager, rate_limit=5, time_period=1, order_timeout=60):
        """
        Initialize TradeExecutor with exchange, trade manager, and budget manager.
        :param exchange: Exchange API client.
        :param trade_manager: Manages trade lifecycle.
        :param budget_manager: Manages strategy budgets.
        :param rate_limit: API rate limit requests per time period.
        :param time_period: Time period for rate limiting in seconds.
        :param order_timeout: Time in seconds before canceling unfilled limit orders.
        """
        self.exchange = exchange
        self.trade_manager = trade_manager
        self.budget_manager = budget_manager
        self.logger = logging.getLogger(self.__class__.__name__)
        self.throttle = Throttler(rate_limit, time_period)
        self.order_timeout = order_timeout

    ### --- Trade Execution ---

    async def execute_trade_with_retry(self, strategy_name, trade_details, retries=3, delay=2):
        """
        Executes a trade with retry logic for transient failures.
        :param strategy_name: Name of the strategy.
        :param trade_details: Trade parameters including asset, side, amount, etc.
        :param retries: Maximum number of retry attempts.
        :param delay: Initial delay between retries (exponential backoff).
        """
        for attempt in range(retries):
            try:
                async with self.throttle:
                    success = await self._execute_trade(strategy_name, trade_details)
                    if success:
                        return True
            except Exception as e:
                self.logger.warning(f"Retry {attempt + 1}/{retries} failed for trade {trade_details['trade_id']}: {e}")
            await asyncio.sleep(delay * (2 ** attempt))  # Exponential backoff
        self.logger.error(f"All retry attempts failed for trade {trade_details['trade_id']}.")
        self.trade_manager.add_failed_trade(trade_details)
        return False

    async def _execute_trade(self, strategy_name, trade_details):
        """
        Executes a trade and records its lifecycle.
        :param strategy_name: Name of the strategy.
        :param trade_details: Trade parameters including asset, side, amount, etc.
        """
        try:
            # Check budget
            budget = self.budget_manager.get_budget(strategy_name)
            if budget <= 0:
                self.logger.error(f"No available budget for strategy '{strategy_name}'.")
                return False

            # Extract trade details
            asset = trade_details["asset"]
            amount = trade_details["amount"]
            leverage = trade_details.get("leverage", 1)
            market_type = trade_details.get("market_type", "spot")

            # Fetch market price
            ticker = await self.exchange.fetch_ticker(asset)
            price = ticker["last"]

            # Budget validation
            if budget < amount * price:
                self.logger.error(f"Insufficient budget for trade {trade_details['trade_id']}.")
                return False

            # Execute market order
            order = await self.exchange.create_order(
                symbol=asset,
                type="market",
                side=trade_details["side"],
                amount=amount,
                params={"leverage": leverage, "type": market_type}
            )

            # Update and record trade
            self.logger.info(f"Trade executed: {order}")
            trade_details.update({"order_id": order["id"], "status": "active", "entry_price": price})
            self.trade_manager.record_trade(trade_details)

            # Set risk management orders
            await self.set_risk_management_orders(
                asset, trade_details["side"], amount, price, 
                trade_details.get("stop_loss"), trade_details.get("take_profit"), trade_details.get("trade_type")
            )
            return True
        except Exception as e:
            self.logger.error(f"Error executing trade: {e}")
            return False

    ### --- Risk Management ---

    async def set_risk_management_orders(self, asset, side, amount, entry_price, stop_loss, take_profit, trade_type):
        """
        Sets stop-loss and take-profit orders for a trade.
        """
        try:
            orders = []

            # Stop-loss order
            if stop_loss:
                sl_price = (
                    entry_price * (1 - stop_loss / 100) if trade_type == "long"
                    else entry_price * (1 + stop_loss / 100)
                )
                sl_order = await self.exchange.create_order(
                    symbol=asset,
                    type="stop",
                    side="sell" if trade_type == "long" else "buy",
                    amount=amount,
                    price=sl_price
                )
                orders.append(sl_order)
                self.logger.info(f"Stop-loss set at {sl_price} for {asset}.")

            # Take-profit order
            if take_profit:
                tp_price = (
                    entry_price * (1 + take_profit / 100) if trade_type == "long"
                    else entry_price * (1 - take_profit / 100)
                )
                tp_order = await self.exchange.create_order(
                    symbol=asset,
                    type="limit",
                    side="sell" if trade_type == "long" else "buy",
                    amount=amount,
                    price=tp_price
                )
                orders.append(tp_order)
                self.logger.info(f"Take-profit set at {tp_price} for {asset}.")

            for order in orders:
                self.trade_manager.record_trade({
                    "order_id": order["id"],
                    "asset": asset,
                    "status": "risk_management",
                    "amount": amount,
                    "price": order.get("price", 0)
                })
        except Exception as e:
            self.logger.error(f"Error setting risk management orders for {asset}: {e}")

    ### --- Fallback Logic ---

    async def fallback_to_market(self, order_id, asset, side, remaining, market_type):
        """
        Cancels a limit order and executes the remaining amount as a market order.
        """
        try:
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
        except Exception as e:
            self.logger.error(f"Error executing fallback to market order for {asset}: {e}")

    ### --- Utility Methods ---

    async def fetch_wallet_balance(self, market_type):
        """
        Fetches wallet balances for the specified market type.
        """
        try:
            balance = await self.exchange.fetch_balance(params={"type": market_type})
            return balance["free"]
        except Exception as e:
            self.logger.error(f"Error fetching wallet balance for {market_type}: {e}")
            return {}

    async def fetch_price(self, asset):
        """
        Fetches the current price of an asset.
        """
        try:
            ticker = await self.exchange.fetch_ticker(asset)
            return ticker["last"]
        except Exception as e:
            self.logger.error(f"Error fetching price for {asset}: {e}")
            return None

    async def close_trade(self, trade_id, reason):
        """
        Closes an active trade and updates its status.
        :param trade_id: ID of the trade to close.
        :param reason: Reason for closing the trade (e.g., stop-loss, take-profit).
        """
        try:
            trade = self.trade_manager.get_trade_by_id(trade_id)
            if not trade:
                self.logger.error(f"Trade {trade_id} not found.")
                return

            side = "sell" if trade["side"] == "buy" else "buy"
            amount = trade["amount"]
            asset = trade["asset"]

            order = await self.exchange.create_order(
                symbol=asset,
                type="market",
                side=side,
                amount=amount,
                params={"type": trade["market_type"]}
            )
            self.logger.info(f"Trade {trade_id} closed: {order}. Reason: {reason}")
            trade.update({"status": "closed", "reason": reason, "close_order_id": order["id"]})
            self.trade_manager.transition_to_closed(trade_id)
        except Exception as e:
            self.logger.error(f"Error closing trade {trade_id}: {e}")
