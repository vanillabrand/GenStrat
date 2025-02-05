import json
import logging
import redis
import asyncio
from typing import List, Dict, Optional
from datetime import datetime
from enum import Enum

class TradeState(Enum):
    PENDING = "pending"
    ACTIVE = "active"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    FAILED = "failed"

class TradeManager:
    """
    Manages the lifecycle of trades, including recording, updating, retrieving, transitioning,
    archiving, and closing trades. Supports handling both pending and active trades with advanced states.
    """

    def __init__(self, redis_host="localhost", redis_port=6379, redis_db=0):
        self.redis_client = redis.StrictRedis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=True
        )
        self.logger = logging.getLogger(self.__class__.__name__)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    ### --- Utility Methods ---

    def _fetch_trades_by_ids(self, trade_ids: List[str]) -> List[Dict]:
        """
        Fetches trade data for multiple trade IDs in one Redis call.
        """
        try:
            pipeline = self.redis_client.pipeline()
            for trade_id in trade_ids:
                pipeline.hgetall(f"trade:{trade_id}")
            return pipeline.execute()
        except Exception as e:
            self.logger.error(f"Failed to fetch trades by IDs: {e}")
            return []

    def _update_trade_status(self, trade_id: str, new_status: str):
        """
        Updates the status of a trade.
        """
        key = f"trade:{trade_id}"
        if self.redis_client.exists(key):
            self.redis_client.hset(key, "status", new_status)
            self.logger.info(f"Trade {trade_id} status updated to {new_status}.")
        else:
            self.logger.error(f"Trade {trade_id} does not exist.")

    ### --- Trade Recording and State Management ---

    def record_trade(self, trade_data: Dict) -> Optional[str]:
        """Records a new trade in Redis."""
        try:
            trade_id = trade_data.get('trade_id', f"trade:{datetime.now().strftime('%Y%m%d%H%M%S')}")
            
            # Set defaults for new fields
            trade_data.setdefault('exchange_order_id', '')  # ID from exchange (once placed)
            trade_data.setdefault('filled_quantity', 0)
            trade_data.setdefault('fee_amount', 0)
            trade_data.setdefault('last_synced_at', '')
            
            trade_data.update({
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
                'status': TradeState.PENDING.value,
                'retry_count': 0
            })

            self.redis_client.hmset(f"trade:{trade_id}", trade_data)
            self.redis_client.sadd("pending_trades", trade_id)
            self.redis_client.sadd(f"strategy:{trade_data['strategy_id']}:trades", trade_id)

            return trade_id
        except Exception as e:
            self.logger.error(f"Failed to record trade: {e}")
            return None

    def add_trade(self, trade_data: Dict) -> Optional[str]:
        """Adds a new trade to the system."""
        try:
            trade_id = self.record_trade(trade_data)
            if trade_id:
                self.logger.info(f"Trade {trade_id} added successfully.")
            return trade_id
        except Exception as e:
            self.logger.error(f"Failed to add trade: {e}")
            return None

    def cancel_trade(self, trade_id: str):
        """Cancels a pending trade."""
        self.transition_trade(trade_id, "pending_trades", "cancelled_trades", TradeState.CANCELLED.value)

    def close_trade(self, trade_id: str):
        """Closes an active trade."""
        self.transition_trade(trade_id, "active_trades", "closed_trades", TradeState.CLOSED.value)

    def add_failed_trade(self, trade_data: Dict):
        """Requeues failed trade with retry logic."""
        try:
            trade_id = trade_data["trade_id"]
            retry_count = trade_data.get("retry_count", 0) + 1

            if retry_count > 3:
                trade_data["status"] = TradeState.FAILED.value
                self.redis_client.hmset(f"trade:{trade_id}", trade_data)
                self.redis_client.srem("pending_trades", trade_id)
                self.redis_client.sadd("failed_trades", trade_id)
                self.logger.error(f"Trade {trade_id} exceeded max retries")
                return

            trade_data.update({
                "status": TradeState.PENDING.value,
                "retry_count": retry_count,
                "last_retry": datetime.now().isoformat()
            })

            self.redis_client.hmset(f"trade:{trade_id}", trade_data)
            self.redis_client.sadd("pending_trades", trade_id)
            self.logger.warning(f"Requeued failed trade: {trade_id}. Retry: {retry_count}/3")

        except Exception as e:
            self.logger.error(f"Failed to requeue trade {trade_id}: {e}")

    def transition_trade(self, trade_id: str, from_set: str, to_set: str, new_status: str):
        """Manages trade state transitions."""
        key = f"trade:{trade_id}"
        try:
            if not self.redis_client.exists(key):
                raise ValueError(f"Trade {trade_id} not found")

            self.redis_client.srem(from_set, trade_id)
            self.redis_client.sadd(to_set, trade_id)
            self.redis_client.hset(key, "status", new_status)
            self.redis_client.hset(key, "updated_at", datetime.now().isoformat())

        except Exception as e:
            self.logger.error(f"Failed to transition trade {trade_id}: {e}")
            raise

    def transition_to_active(self, trade_id: str):
        """
        Moves a trade from pending to active status.
        """
        self.transition_trade(trade_id, "pending_trades", "active_trades", TradeState.ACTIVE.value)

    def transition_to_closed(self, trade_id: str):
        """
        Moves a trade to the closed state.
        """
        self.transition_trade(trade_id, "active_trades", "closed_trades", TradeState.CLOSED.value)

    def archive_trade(self, trade_id: str):
        """
        Archives a trade and removes it from active storage.
        """
        key = f"trade:{trade_id}"
        archive_key = f"archive:trade:{trade_id}"
        try:
            if self.redis_client.exists(key):
                trade_data = self.redis_client.hgetall(key)
                self.redis_client.set(archive_key, json.dumps(trade_data))
                self.redis_client.delete(key)
                self.logger.info(f"Trade {trade_id} archived successfully.")
            else:
                self.logger.error(f"Trade ID '{trade_id}' does not exist.")
        except Exception as e:
            self.logger.error(f"Failed to archive trade {trade_id}: {e}")

    ### --- Trade Retrieval and Monitoring ---

    def get_active_trades(self) -> List[Dict]:
        """
        Retrieves all active trades from the database.
        """
        try:
            trade_ids = self.redis_client.smembers("active_trades")
            trades = self._fetch_trades_by_ids(list(trade_ids))
            return trades
        except Exception as e:
            self.logger.error(f"Failed to retrieve active trades: {e}")
            return []

    def get_pending_trades(self) -> List[Dict]:
        """
        Retrieves all pending trades from the database.
        """
        try:
            trade_ids = self.redis_client.smembers("pending_trades")
            trades = self._fetch_trades_by_ids(list(trade_ids))
            return trades
        except Exception as e:
            self.logger.error(f"Failed to retrieve pending trades: {e}")
            return []

    def get_trade(self, trade_id: str) -> Optional[Dict]:
        """Retrieves trade by ID."""
        try:
            trade = self.redis_client.hgetall(f"trade:{trade_id}")
            return trade if trade else None
        except Exception as e:
            self.logger.error(f"Failed to get trade {trade_id}: {e}")
            return None

    def update_trade(self, trade_id: str, updates: Dict) -> bool:
        """Updates existing trade."""
        try:
            updates['updated_at'] = datetime.now().isoformat()
            self.redis_client.hmset(f"trade:{trade_id}", updates)
            return True
        except Exception as e:
            self.logger.error(f"Failed to update trade {trade_id}: {e}")
            return False

    def get_strategy_trades(self, strategy_id: str, status: Optional[str] = None) -> List[Dict]:
        """Retrieves all trades for a strategy."""
        try:
            trade_ids = self.redis_client.smembers(f"strategy:{strategy_id}:trades")
            trades = self._fetch_trades_by_ids(list(trade_ids))
            if status:
                trades = [t for t in trades if t.get('status') == status]
            return trades
        except Exception as e:
            self.logger.error(f"Failed to get strategy trades: {e}")
            return []

    def close_strategy_trades(self, strategy_id: str) -> bool:
        """Closes all active trades for a strategy."""
        try:
            active_trades = self.get_strategy_trades(strategy_id, TradeState.ACTIVE.value)
            for trade in active_trades:
                self.transition_trade(
                    trade['trade_id'],
                    "active_trades",
                    "closed_trades",
                    TradeState.CLOSED.value
                )
            return True
        except Exception as e:
            self.logger.error(f"Failed to close strategy trades: {e}")
            return False

    def get_trade_performance(self, trade_id: str) -> Dict:
        """Calculates trade performance metrics."""
        try:
            trade = self.get_trade(trade_id)
            if not trade:
                return {}

            entry_price = float(trade['entry_price'])
            current_price = float(trade['current_price'])
            position_size = float(trade['amount'])

            pnl = (current_price - entry_price) * position_size if trade['side'] == 'buy' \
                else (entry_price - current_price) * position_size

            return {
                'pnl': pnl,
                'roi': (pnl / (entry_price * position_size)) * 100,
                'duration': (datetime.now() - datetime.fromisoformat(trade['created_at'])).seconds
            }
        except Exception as e:
            self.logger.error(f"Failed to calculate trade performance: {e}")
            return {}

    def get_strategy_performance(self, strategy_id: str) -> Dict:
        """Calculates strategy performance metrics."""
        try:
            trades = self.get_strategy_trades(strategy_id)
            performances = [self.get_trade_performance(t['trade_id']) for t in trades]

            total_pnl = sum(p.get('pnl', 0) for p in performances)
            win_count = len([p for p in performances if p.get('pnl', 0) > 0])

            return {
                'total_pnl': total_pnl,
                'win_rate': (win_count / len(performances)) if performances else 0,
                'total_trades': len(trades),
                'active_trades': len([t for t in trades if t['status'] == TradeState.ACTIVE.value])
            }
        except Exception as e:
            self.logger.error(f"Failed to calculate strategy performance: {e}")
            return {}

    async def monitor_pending_trades(self, market_monitor, trade_executor):
        """
        Asynchronously monitors pending trades and executes them when entry conditions are met.
        """
        self.logger.info("Starting pending-trade monitoring loop...")
        while True:
            pending_trades = self.get_pending_trades()
            tasks = [
                self._process_trade(trade, market_monitor, trade_executor)
                for trade in pending_trades
            ]
            await asyncio.gather(*tasks)
            await asyncio.sleep(5)

    async def _process_trade(self, trade: Dict, market_monitor, trade_executor):
        """
        Processes a single pending trade.
        """
        try:
            if market_monitor.check_entry_conditions(trade):
                self.logger.info(f"Entry condition met for {trade['asset']}. Executing trade.")
                await trade_executor.execute_trade(
                    trade["strategy_name"],
                    trade["asset"],
                    trade["side"],
                    trade
                )
                self.transition_to_active(trade["trade_id"])
            else:
                self.logger.debug(f"Conditions not met for {trade['asset']}. Trade remains pending.")
        except Exception as e:
            self.logger.error(f"Error processing trade {trade['trade_id']}: {e}")

    def cleanup_old_trades(self, days: int = 30) -> int:
        """Removes trades older than specified days."""
        try:
            cutoff = datetime.now().timestamp() - (days * 24 * 60 * 60)
            cleaned = 0

            for key in self.redis_client.scan_iter("trade:*"):
                trade = self.redis_client.hgetall(key)
                if trade and datetime.fromisoformat(trade['created_at']).timestamp() < cutoff:
                    self.redis_client.delete(key)
                    cleaned += 1

            return cleaned
        except Exception as e:
            self.logger.error(f"Failed to cleanup old trades: {e}")
            return 0

    ### --- NEW METHODS FOR EXCHANGE & AI RECONCILIATION ---

    def sync_with_exchange(self, exchange_client, strategy_id=None):
        """
        Reconciles local trades with the exchange. 
        Fetches status/fill info from the exchange for trades with an exchange_order_id.
        Updates local trades to match actual state on the exchange.
        
        :param exchange_client: A client or wrapper that can fetch order data via e.g. exchange_client.get_order_status(order_id)
        :param strategy_id: (optional) If provided, only reconcile trades for this strategy.
        """
        if strategy_id:
            active_trades = self.get_strategy_trades(strategy_id, status=TradeState.ACTIVE.value)
            pending_trades = self.get_strategy_trades(strategy_id, status=TradeState.PENDING.value)
        else:
            active_trades = self.get_active_trades()
            pending_trades = self.get_pending_trades()

        trades_to_reconcile = active_trades + pending_trades

        for trade in trades_to_reconcile:
            exchange_order_id = trade.get("exchange_order_id")
            if not exchange_order_id:
                # Possibly not placed on the exchange yet
                continue

            try:
                exchange_order_data = exchange_client.get_order_status(exchange_order_id)
                if not exchange_order_data:
                    self.logger.warning(f"No data returned from exchange for {exchange_order_id}")
                    continue

                filled_qty = float(exchange_order_data.get("filled_qty", 0.0))
                new_status = exchange_order_data.get("status", "").lower()
                local_filled = float(trade.get("filled_quantity", 0.0))

                # Update partial fill if changed
                updates = {}
                if filled_qty != local_filled:
                    updates["filled_quantity"] = filled_qty

                # Map exchange status to local status
                # e.g. "filled", "partially_filled", "canceled", etc.
                if new_status == "filled" and trade["status"] != TradeState.CLOSED.value:
                    # Mark trade as closed
                    if trade["status"] == TradeState.ACTIVE.value:
                        self.transition_trade(trade["trade_id"], "active_trades", "closed_trades", TradeState.CLOSED.value)
                    elif trade["status"] == TradeState.PENDING.value:
                        # If for some reason exchange says filled but locally it was still pending
                        self.transition_trade(trade["trade_id"], "pending_trades", "closed_trades", TradeState.CLOSED.value)

                elif new_status == "canceled" and trade["status"] not in (TradeState.CLOSED.value, TradeState.CANCELLED.value):
                    # Mark trade as cancelled
                    if trade["status"] == TradeState.PENDING.value:
                        self.transition_trade(trade["trade_id"], "pending_trades", "cancelled_trades", TradeState.CANCELLED.value)
                    elif trade["status"] == TradeState.ACTIVE.value:
                        self.transition_trade(trade["trade_id"], "active_trades", "cancelled_trades", TradeState.CANCELLED.value)

                # Save the moment we synced
                updates["last_synced_at"] = datetime.now().isoformat()

                if updates:
                    self.update_trade(trade["trade_id"], updates)

            except Exception as e:
                self.logger.error(f"Error reconciling trade {trade['trade_id']} with exchange: {e}")

    async def monitor_active_trades(self, market_monitor, trade_executor):
        """
        Asynchronously checks active trades for exit conditions or partial fill updates.
        Similar to monitor_pending_trades, but focuses on trades that are already active.
        """
        self.logger.info("Starting active-trade monitoring loop...")
        while True:
            active_trades = self.get_active_trades()
            tasks = [
                self._process_active_trade(trade, market_monitor, trade_executor)
                for trade in active_trades
            ]
            await asyncio.gather(*tasks)
            await asyncio.sleep(5)

    async def _process_active_trade(self, trade: Dict, market_monitor, trade_executor):
        """
        Checks exit conditions for a single active trade. If exit conditions are met, close the trade.
        Optionally re-validate with AI or partial fill updates, etc.
        """
        try:
            if market_monitor.check_exit_conditions(trade):
                self.logger.info(f"Exit condition met for {trade['asset']}. Closing trade.")
                await trade_executor.close_trade(
                    trade["strategy_name"],
                    trade["asset"],
                    trade["side"],
                    trade
                )
                self.transition_to_closed(trade["trade_id"])
            else:
                self.logger.debug(f"Exit conditions not met for {trade['asset']}. Trade remains active.")
        except Exception as e:
            self.logger.error(f"Error processing active trade {trade['trade_id']}: {e}")

    def revalidate_trades_with_ai(self, ai_client):
        """
        Example method to demonstrate how you'd re-check trades with AI.
        In practice, you'd pass relevant trade & market data to the AI, and handle suggestions.
        """
        try:
            # Optionally retrieve trades you want to re-check (e.g. all active)
            trades_to_revalidate = self.get_active_trades()

            for trade in trades_to_revalidate:
                # Gather data for AI
                # This might include trade details, current market price, or candle data
                ai_input = {
                    "trade": trade,
                    "market_conditions": {}  # you'd fill this from MarketMonitor or exchange data
                }
                suggestion = ai_client.analyze_trade(ai_input)
                if suggestion.get("action") == "amend":
                    self.logger.info(f"AI suggests amending trade {trade['trade_id']}.")
                    # In a real scenario, you'd schedule an update or talk to TradeExecutor
                elif suggestion.get("action") == "close":
                    self.logger.info(f"AI suggests closing trade {trade['trade_id']}.")
                    # Trigger a close or set a flag for exit
        except Exception as e:
            self.logger.error(f"Error during AI revalidation: {e}")
