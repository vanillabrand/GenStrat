import asyncio
import logging


class TradeMonitor:
    """
    Monitors active trades and validates trade conditions.
    """

    def __init__(self, trade_manager, trade_executor, performance_manager):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.trade_manager = trade_manager
        self.trade_executor = trade_executor
        self.performance_manager = performance_manager  # NEW: Performance manager integration

    async def monitor_active_trades(self):
        """Main loop to monitor and update active trades."""
        while True:
            try:
                active_trades = self.performance_manager.get_active_trades()  # Pull active trades
                for trade in active_trades:
                    await self.check_trade_conditions(trade)
            except Exception as e:
                self.logger.error(f"Error monitoring trades: {e}")
            await asyncio.sleep(5)  # Refresh every 5 seconds

    async def check_trade_conditions(self, trade):
        """Checks conditions for an active trade."""
        try:
            current_price = await self.trade_executor.fetch_price(trade["asset"])
            entry_price = float(trade.get("entry_price", 0))
            stop_loss = float(trade.get("stop_loss", 0))
            take_profit = float(trade.get("take_profit", 0))

            # Check for stop-loss
            if stop_loss and current_price <= stop_loss:
                self.logger.info(f"Trade {trade['trade_id']} hit stop-loss at {current_price}.")
                await self.trade_executor.close_trade(trade["trade_id"], "stop_loss")
                return

            # Check for take-profit
            if take_profit and current_price >= take_profit:
                self.logger.info(f"Trade {trade['trade_id']} hit take-profit at {current_price}.")
                await self.trade_executor.close_trade(trade["trade_id"], "take_profit")
                return

            self.logger.info(f"Trade {trade['trade_id']} is still active.")
        except Exception as e:
            self.logger.error(f"Error checking conditions for trade {trade['trade_id']}: {e}")
