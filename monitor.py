# monitor.py

import logging
from typing import List, Dict
import csv

class Monitor:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)
        
        # Console handler for logging
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        
        # Formatter for the logs
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        
        # Avoid adding multiple handlers if already present
        if not self.logger.handlers:
            self.logger.addHandler(ch)
        
        self.trades: List[Dict] = []

    def log_trade(self, trade_info: Dict):
        """
        Logs the trade information.
        
        Args:
            trade_info (Dict): Dictionary containing trade details.
        """
        self.trades.append(trade_info)
        self.logger.info(f"Trade Executed: {trade_info}")
    
    def get_trades(self) -> List[Dict]:
        """
        Returns the list of logged trades.
        
        Returns:
            List[Dict]: List of trade details.
        """
        return self.trades

    def export_trades_to_csv(self, filename: str):
        """
        Exports the logged trades to a CSV file.
        
        Args:
            filename (str): The name of the CSV file.
        """
        if not self.trades:
            self.logger.info("No trades to export.")
            return

        keys = self.trades[0].keys()
        with open(filename, 'w', newline='') as output_file:
            dict_writer = csv.DictWriter(output_file, keys)
            dict_writer.writeheader()
            dict_writer.writerows(self.trades)
        self.logger.info(f"Trades exported to {filename}")
