import asyncio
import logging
from typing import Dict, List
from rich.table import Table
from rich.live import Live

class TradeMonitor:
    """
    Monitors active trades, updates statuses, adapts trades dynamically, and provides live feedback.
    """

    def __init__(self, exchange, trade_manager, performance_manager):
        self.exchange = exchange
        self.trade_manager = trade_manager
        self.performance_manager = performance_manager
        self.logger = logging.getLogger(self.__class__.__name__)
        self.live_dashboard = None

    def create_dashboard(self):
        """
        Creates the live dashboard structure.
        """
        table = Table(title="Live Trade Monitoring")
        table.add_column("Trade ID", justify="center", style="cyan", no_wrap=True)
        table.add_column("Strategy Name", justify="center", style="green", no_wrap=True)
        table.add_column("Asset", justify="center", style="magenta", no_wrap=True)
        table.add_column("Status", justify="center", style="yellow", no_wrap=True)
        table.add_column("PnL", justify="center", style="red", no_wrap=True)
        table.add_column("Last Action", justify="center", style="blue", no_wrap=True)
        return table

    async def start_monitoring(self, interval: int = 10):
        """
        Start monitoring trades and updating their statuses.
        :param interval: Time in seconds between updates.
        """
        self.logger.info("Trade monitoring started.")
        self.live_dashboard = self.create_dashboard()
        with Live(self.live_dashboard, refresh_per_second=1) as live:
            while True:
                try:
                    await self.update_trades()
                    self.update_dashboard()
                except Exception as e:
                    self.logger.error(f"Error during trade monitoring: {e}")
                await asyncio.sleep(interval)

    async def update_trades(self):
        """
        Fetches and updates the status of active trades, adapting them if needed.
        """
        active_trades = self.trade_manager.get_active_trades()
        for trade in active_trades:
            try:
                order = await self.exchange.fetch_order(trade['order_id'], trade['asset'])
                updates = {
                    'status': order['status'],
                    'filled': order.get('filled', 0),
                    'remaining': order.get('remaining', 0),
                    'average': order.get('average', 0),
                    'pnl': self.calculate_pnl(trade, order)
                }
                self.trade_manager.update_trade(trade['trade_id'], updates)
                self.logger.debug(f"Trade '{trade['trade_id']}' status updated.")
                await self.adapt_trade(trade, order)
            except Exception as e:
                self.logger.error(f"Error updating trade {trade['trade_id']}: {e}")

    async def adapt_trade(self, trade: Dict, order: Dict):
        """
        Adapts a trade based on new market conditions or strategy updates.
        :param trade: The trade being monitored.
        :param order: Current order details from the exchange.
        """
        try:
            strategy_name = trade['strategy_name']
            updated_conditions = self.trade_manager.get_strategy_conditions(strategy_name)

            if 'exit' in updated_conditions:
                new_exit_price = self.calculate_exit_price(order, updated_conditions['exit'])
                if new_exit_price != order.get('price'):
                    await self.exchange.modify_order(
                        order_id=order['id'],
                        symbol=trade['asset'],
                        price=new_exit_price
                    )
                    self.logger.info(f"Adjusted exit price for trade {trade['trade_id']} to {new_exit_price}.")
        except Exception as e:
            self.logger.error(f"Error adapting trade {trade['trade_id']}: {e}")

    def calculate_pnl(self, trade: Dict, order: Dict) -> float:
        """
        Calculates profit and loss for a trade.
        :param trade: Trade details.
        :param order: Current order details.
        :return: Calculated PnL.
        """
        entry_price = trade.get('entry_price', 0)
        exit_price = order.get('average', 0)
        amount = order.get('filled', 0)
        pnl = (exit_price - entry_price) * amount if trade['side'] == 'buy' else (entry_price - exit_price) * amount
        return pnl

    def calculate_exit_price(self, order: Dict, exit_conditions: Dict) -> float:
        """
        Calculates a new exit price based on updated conditions.
        :param order: Current order details.
        :param exit_conditions: Updated exit conditions.
        :return: New exit price.
        """
        exit_price = order['price'] * 1.02  # Placeholder logic for a 2% target profit
        return exit_price

    def update_dashboard(self):
        """
        Updates the live dashboard table with the latest trade information.
        """
        self.live_dashboard.rows.clear()
        active_trades = self.trade_manager.get_active_trades()
        for trade in active_trades:
            status = trade.get('status', 'Unknown')
            pnl = trade.get('pnl', 0.0)
            self.live_dashboard.add_row(
                trade['trade_id'],
                trade['strategy_name'],
                trade['asset'],
                status,
                f"{pnl:.2f}",
                trade.get('last_action', 'N/A')
            )
