import asyncio
import logging
from typing import Dict, List


class MarketMonitor:
    """
    Monitors market conditions via WebSocket, evaluates entry/exit conditions for trades,
    and collaborates with TradeMonitor and TradeSuggestionManager for strategy management.
    """
    def __init__(self, exchange, trade_monitor, trade_suggestion_manager):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.exchange = exchange  # WebSocket-enabled exchange object
        self.trade_monitor = trade_monitor  # Handles trade execution and status updates
        self.trade_suggestion_manager = trade_suggestion_manager  # Handles OpenAI integration
        self.monitored_strategies = {}  # Stores strategies and their associated trades
        self.active_assets = set()  # Tracks assets currently being monitored

    def monitor_strategy(self, strategy: Dict, trades: List[Dict]):
        """
        Adds a strategy and its trades to the monitoring list.
        """
        strategy_id = strategy["id"]
        self.monitored_strategies[strategy_id] = {"strategy": strategy, "trades": trades}
        self.active_assets.update(trade["asset"] for trade in trades)
        self.logger.info(f"Monitoring strategy {strategy_id} with {len(trades)} trades.")

    async def deactivate_strategy(self, strategy_id: str):
        """
        Deactivates a strategy by removing it and its trades from monitoring.
        """
        if strategy_id in self.monitored_strategies:
            strategy_data = self.monitored_strategies.pop(strategy_id)
            trades = strategy_data["trades"]
            assets = [trade["asset"] for trade in trades]

            # Mark trades as inactive
            for trade in trades:
                trade["status"] = "inactive"
                await self.trade_monitor.deactivate_trade(trade["trade_id"])

            # Remove assets from active monitoring
            self.active_assets.difference_update(assets)
            self.logger.info(f"Strategy {strategy_id} and its trades have been deactivated.")
        else:
            self.logger.warning(f"Strategy {strategy_id} is not being monitored.")

    async def start_websocket_monitoring(self):
        """
        Monitors real-time market data for all strategies and trades.
        """
        self.logger.info("Starting WebSocket monitoring...")
        try:
            while True:
                try:
                    # Stream live data for all active assets
                    if not self.active_assets:
                        self.logger.info("No active assets to monitor. Sleeping...")
                        await asyncio.sleep(5)
                        continue

                    # Ensure `watchTradesForSymbols` is awaited correctly
                    async for live_trades in self.exchange.watchTradesForSymbols(list(self.active_assets)):
                        await self.process_ticker_updates(live_trades)

                except Exception as e:
                    self.logger.error(f"WebSocket monitoring error: {e}. Retrying...")
                    await asyncio.sleep(1)  # Retry after a short delay

        except asyncio.CancelledError:
            self.logger.info("WebSocket monitoring stopped.")
        except Exception as e:
            self.logger.error(f"Unexpected error in WebSocket monitoring: {e}", exc_info=True)

    async def process_ticker_updates(self, updates: List[Dict]):
        """
        Processes a batch of WebSocket ticker updates.
        """
        for update in updates:
            asset = update.get("symbol")
            if not asset or asset not in self.active_assets:
                continue  # Skip unrelated assets

            # Notify TradeMonitor of updates (correctly awaited)
            await self.trade_monitor.evaluate_trades(asset, update)

    async def review_with_openai(self):
        """
        Periodically sends strategies, trades, and market data to OpenAI for review and recommendations.
        """
        try:
            for strategy_id, data in self.monitored_strategies.items():
                strategy = data["strategy"]
                trades = data["trades"]
                assets = [trade["asset"] for trade in trades]

                # Fetch current market data (await correctly)
                market_data = await self.trade_suggestion_manager.fetch_market_data(assets)

                # Send to OpenAI for review (await correctly)
                recommendations = await self.trade_suggestion_manager.review_trades_with_openai(strategy, trades, market_data)

                # Process recommendations
                for recommendation in recommendations:
                    processed_trade = self.trade_suggestion_manager.process_trade_for_storage(recommendation, market_data)
                    if processed_trade:
                        await self.trade_monitor.add_or_update_trade(processed_trade)

                self.logger.info(f"OpenAI review complete for strategy {strategy_id}.")
        except Exception as e:
            self.logger.error(f"Error during OpenAI review: {e}", exc_info=True)
