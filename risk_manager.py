# risk_manager.py

from typing import Dict


class RiskManager:
    """
    Manages risk parameters for strategies.
    """

    def __init__(self):
        # Define default risk parameters for different risk levels
        self.risk_levels = {
            'low': {'stop_loss': 2, 'take_profit': 5, 'trailing_stop_loss': 1},
            'medium': {'stop_loss': 5, 'take_profit': 10, 'trailing_stop_loss': 2},
            'high': {'stop_loss': 10, 'take_profit': 20, 'trailing_stop_loss': 5},
        }

    def suggest_risk_parameters(self, risk_level: str) -> Dict:
        """
        Suggests risk parameters based on the risk level.
        """
        risk_params = self.risk_levels.get(risk_level.lower())
        if not risk_params:
            raise ValueError(f"Unsupported risk level: {risk_level}")
        return risk_params

    def validate_risk_parameters(self, risk_params: Dict):
        """
        Validates the risk parameters.
        """
        required_keys = ['stop_loss', 'take_profit', 'trailing_stop_loss']
        for key in required_keys:
            if key not in risk_params:
                raise ValueError(f"Missing risk parameter: {key}")
            if not isinstance(risk_params[key], (int, float)) or risk_params[key] < 0:
                raise ValueError(f"Invalid value for {key}: {risk_params[key]}")

    def update_risk_parameters(self, strategy_data: Dict, risk_params: Dict):
        """
        Updates the risk parameters in the strategy data.
        """
        self.validate_risk_parameters(risk_params)
        strategy_data['risk_management'] = risk_params
