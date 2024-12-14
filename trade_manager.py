import asyncio
import logging
from typing import Dict, List

class TradeMonitor:
    """
    Monitors active trades, updates statuses, and calculates performance metrics for strategies.
    """

    def __init__(self, exchange, trade_manager, performance_manager):
        self.exchange = exchange
        self.trade_manager = trade_manager
        self.performance_manager = performance_manager
        self.logger = logging.getLogger(self.__class__.__name__)

    async def start_monitoring(self, interval: int = 10):
        """
        Start monitoring trades and update them periodically.
        :param interval: Time in seconds between updates.
        """
        self.logger.info("Trade monitoring started.")
        while True:
            try:
                await self.update_trades()
            except Exception as e:
                self.logger.error(f"Error during trade monitoring: {e}")
            await asyncio.sleep(interval)

    async def update_trades(self):
        """
        Fetch and update the status of active trades.
        """
        active_trades = self.trade_manager.get_active_trades()
        strategies = {}

        for trade in active_trades:
            try:
                self.logger.info(f"Updating trade {trade['trade_id']} for strategy {trade['strategy_name']}")
                order = await self.exchange.fetch_order(trade['order_id'], trade['asset'])
                updates = {
                    'status': order['status'],
                    'filled': order.get('filled', 0),
                    'remaining': order.get('remaining', 0),
                    'average': order.get('average', 0)
                }
                self.trade_manager.update_trade(trade['trade_id'], updates)
                self.logger.debug(f"Trade '{trade['trade_id']}' status updated: {updates}")

                # Collect data for performance metrics
                strategy_name = trade['strategy_name']
                if strategy_name not in strategies:
                    strategies[strategy_name] = []
                strategies[strategy_name].append(trade)
            except Exception as e:
                self.logger.error(f"Error updating trade {trade['trade_id']}: {e}")

        # Update performance metrics for each strategy
        for strategy_name, trades in strategies.items():
            performance_data = self.calculate_performance(trades)
            self.performance_manager.record_performance(strategy_name, performance_data)

    def calculate_performance(self, trades: List[Dict]) -> Dict:
        """
        Calculate performance metrics for a list of trades.
        :param trades: List of trades to analyze.
        :return: Dictionary containing performance metrics.
        """
        total_pnl = 0
        total_investment = 0
        wins = 0
        losses = 0
        max_drawdown = 0
        equity_curve = []
        equity = 0

        for trade in trades:
            if trade['status'] == 'closed':
                entry_price = float(trade.get('entry_price', 0))
                exit_price = float(trade.get('average', 0))
                amount = float(trade.get('filled', 0))
                pnl = (exit_price - entry_price) * amount if trade['side'] == 'buy' else (entry_price - exit_price) * amount
                total_pnl += pnl
                total_investment += entry_price * amount
                equity += pnl
                equity_curve.append(equity)

                if pnl > 0:
                    wins += 1
                else:
                    losses += 1

        win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        roi = (total_pnl / total_investment * 100) if total_investment > 0 else 0
        avg_profit = (total_pnl / (wins + losses)) if (wins + losses) > 0 else 0

        if equity_curve:
            peak = equity_curve[0]
            for value in equity_curve:
                if value > peak:
                    peak = value
                drawdown = ((peak - value) / peak) * 100 if peak > 0 else 0
                max_drawdown = max(max_drawdown, drawdown)

        performance_data = {
            'total_pnl': total_pnl,
            'roi': roi,
            'win_rate': win_rate,
            'avg_profit': avg_profit,
            'max_drawdown': max_drawdown
        }
        self.logger.debug(f"Calculated performance metrics: {performance_data}")
        return performance_data

    async def send_alert(self, trade: Dict, message: str):
        """
        Sends an alert for a specific trade.
        :param trade: Trade details.
        :param message: Alert message to send.
        """
        self.logger.info(f"Alert for trade {trade['trade_id']}: {message}")
