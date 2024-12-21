import logging
from typing import Dict, Union


class RiskManager:
    """
    Manages risk for trades and strategies, including calculations for position sizing,
    leverage, stop-loss, take-profit, and other risk parameters.
    """

    def __init__(self, max_risk_per_trade: float = 0.02, max_total_risk: float = 0.1):
        """
        Initialize the RiskManager with risk parameters.
        :param max_risk_per_trade: Maximum risk per trade as a fraction of total capital.
        :param max_total_risk: Maximum total risk across all active trades.
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.max_risk_per_trade = max_risk_per_trade
        self.max_total_risk = max_total_risk
        self.active_trade_risks = {}

    def calculate_position_size(
        self, account_balance: float, entry_price: float, stop_loss: float
    ) -> float:
        """
        Calculates the position size based on risk parameters.
        :param account_balance: Total available account balance.
        :param entry_price: Entry price for the trade.
        :param stop_loss: Stop-loss price for the trade.
        :return: Position size in terms of the asset amount.
        """
        try:
            risk_per_unit = abs(entry_price - stop_loss)
            max_risk_amount = self.max_risk_per_trade * account_balance
            position_size = max_risk_amount / risk_per_unit
            self.logger.info(
                f"Calculated position size: {position_size} units with risk per unit: {risk_per_unit}"
            )
            return position_size
        except Exception as e:
            self.logger.error(f"Failed to calculate position size: {e}")
            return 0.0

    def validate_trade_risk(
        self,
        strategy_name: str,
        account_balance: float,
        entry_price: float,
        stop_loss: float,
    ) -> bool:
        """
        Validates if the trade risk is within allowable limits.
        :param strategy_name: Name of the strategy.
        :param account_balance: Total available account balance.
        :param entry_price: Entry price for the trade.
        :param stop_loss: Stop-loss price for the trade.
        :return: True if trade risk is valid, False otherwise.
        """
        try:
            risk_per_trade = abs(entry_price - stop_loss) / entry_price
            total_active_risk = sum(self.active_trade_risks.values())
            if risk_per_trade > self.max_risk_per_trade:
                self.logger.warning(
                    f"Trade for strategy '{strategy_name}' exceeds max risk per trade."
                )
                return False
            if total_active_risk + risk_per_trade > self.max_total_risk:
                self.logger.warning(
                    f"Trade for strategy '{strategy_name}' exceeds max total risk."
                )
                return False

            self.logger.info(
                f"Trade for strategy '{strategy_name}' validated with risk: {risk_per_trade}."
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to validate trade risk: {e}")
            return False

    def record_trade_risk(self, trade_id: str, risk_amount: float):
        """
        Records the risk amount associated with an active trade.
        :param trade_id: Unique identifier of the trade.
        :param risk_amount: Risk amount for the trade.
        """
        try:
            self.active_trade_risks[trade_id] = risk_amount
            self.logger.info(f"Recorded risk for trade '{trade_id}': {risk_amount}")
        except Exception as e:
            self.logger.error(f"Failed to record trade risk for trade '{trade_id}': {e}")

    def remove_trade_risk(self, trade_id: str):
        """
        Removes the risk record for a closed or canceled trade.
        :param trade_id: Unique identifier of the trade.
        """
        try:
            if trade_id in self.active_trade_risks:
                del self.active_trade_risks[trade_id]
                self.logger.info(f"Removed risk record for trade '{trade_id}'.")
            else:
                self.logger.warning(f"No risk record found for trade '{trade_id}'.")
        except Exception as e:
            self.logger.error(f"Failed to remove trade risk for trade '{trade_id}': {e}")

    def calculate_stop_loss(self, entry_price: float, risk_percent: float) -> float:
        """
        Calculates the stop-loss price based on entry price and risk percentage.
        :param entry_price: Entry price for the trade.
        :param risk_percent: Risk percentage for the stop-loss.
        :return: Calculated stop-loss price.
        """
        try:
            stop_loss = entry_price * (1 - risk_percent)
            self.logger.info(
                f"Calculated stop-loss: {stop_loss} for entry price: {entry_price} with risk percent: {risk_percent}"
            )
            return stop_loss
        except Exception as e:
            self.logger.error(f"Failed to calculate stop-loss: {e}")
            return 0.0

    def calculate_take_profit(self, entry_price: float, reward_percent: float) -> float:
        """
        Calculates the take-profit price based on entry price and reward percentage.
        :param entry_price: Entry price for the trade.
        :param reward_percent: Reward percentage for the take-profit.
        :return: Calculated take-profit price.
        """
        try:
            take_profit = entry_price * (1 + reward_percent)
            self.logger.info(
                f"Calculated take-profit: {take_profit} for entry price: {entry_price} with reward percent: {reward_percent}"
            )
            return take_profit
        except Exception as e:
            self.logger.error(f"Failed to calculate take-profit: {e}")
            return 0.0

    def adjust_risk_parameters(
        self, strategy_name: str, new_risk_per_trade: float, new_total_risk: float
    ):
        """
        Adjusts the risk parameters for a strategy.
        :param strategy_name: Name of the strategy.
        :param new_risk_per_trade: New maximum risk per trade.
        :param new_total_risk: New maximum total risk.
        """
        try:
            self.max_risk_per_trade = new_risk_per_trade
            self.max_total_risk = new_total_risk
            self.logger.info(
                f"Adjusted risk parameters for '{strategy_name}': Max Risk Per Trade: {new_risk_per_trade}, Max Total Risk: {new_total_risk}"
            )
        except Exception as e:
            self.logger.error(f"Failed to adjust risk parameters for '{strategy_name}': {e}")
