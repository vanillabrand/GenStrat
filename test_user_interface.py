import unittest
from unittest.mock import patch, MagicMock
from user_interface import UserInterface

class TestUserInterface(unittest.TestCase):

    @patch('builtins.input', side_effect=['1', 'path/to/historical_data.csv'])
    @patch('pandas.read_csv')
    @patch('user_interface.UserInterface.get_strategy_selection')
    @patch('user_interface.UserInterface.console')
    @patch('user_interface.UserInterface.backtester')
    def test_run_backtests_load_csv(self, mock_backtester, mock_console, mock_get_strategy_selection, mock_read_csv, mock_input):
        # Mock strategy selection
        mock_get_strategy_selection.return_value = {'id': 'strategy1', 'title': 'Test Strategy'}

        # Mock historical data
        mock_read_csv.return_value = MagicMock()

        # Create UserInterface instance
        ui = UserInterface(exchange='test_exchange')

        # Run the method
        ui.run_backtests()

        # Assertions
        mock_get_strategy_selection.assert_called_once_with("Select a strategy to run backtests")
        mock_read_csv.assert_called_once_with('path/to/historical_data.csv')
        mock_backtester.run_backtest.assert_called_once_with('strategy1', mock_read_csv.return_value)
        mock_console.print.assert_any_call("[bold green]Backtest completed for strategy 'Test Strategy'.[/bold green]")

    @patch('builtins.input', side_effect=['2', '1m', '30'])
    @patch('user_interface.UserInterface.get_strategy_selection')
    @patch('user_interface.UserInterface.console')
    @patch('user_interface.UserInterface.backtester')
    def test_run_backtests_generate_synthetic_data(self, mock_backtester, mock_console, mock_get_strategy_selection, mock_input):
        # Mock strategy selection
        mock_get_strategy_selection.return_value = {'id': 'strategy1', 'title': 'Test Strategy'}

        # Mock synthetic data generation
        mock_backtester.generate_synthetic_data.return_value = MagicMock()

        # Create UserInterface instance
        ui = UserInterface(exchange='test_exchange')

        # Run the method
        ui.run_backtests()

        # Assertions
        mock_get_strategy_selection.assert_called_once_with("Select a strategy to run backtests")
        mock_backtester.generate_synthetic_data.assert_called_once_with('1m', 30)
        mock_backtester.run_backtest.assert_called_once_with('strategy1', mock_backtester.generate_synthetic_data.return_value)
        mock_console.print.assert_any_call("[bold green]Backtest completed for strategy 'Test Strategy'.[/bold green]")

    @patch('builtins.input', side_effect=['3'])
    @patch('user_interface.UserInterface.get_strategy_selection')
    @patch('user_interface.UserInterface.console')
    def test_run_backtests_invalid_choice(self, mock_console, mock_get_strategy_selection, mock_input):
        # Mock strategy selection
        mock_get_strategy_selection.return_value = {'id': 'strategy1', 'title': 'Test Strategy'}

        # Create UserInterface instance
        ui = UserInterface(exchange='test_exchange')

        # Run the method
        ui.run_backtests()

        # Assertions
        mock_get_strategy_selection.assert_called_once_with("Select a strategy to run backtests")
        mock_console.print.assert_any_call("[bold red]Invalid choice.[/bold red]")

    @patch('user_interface.UserInterface.get_strategy_selection')
    @patch('user_interface.UserInterface.console')
    def test_run_backtests_no_strategy_selected(self, mock_console, mock_get_strategy_selection):
        # Mock no strategy selection
        mock_get_strategy_selection.return_value = None

        # Create UserInterface instance
        ui = UserInterface(exchange='test_exchange')

        # Run the method
        ui.run_backtests()

        # Assertions
        mock_get_strategy_selection.assert_called_once_with("Select a strategy to run backtests")
        mock_console.print.assert_not_called()

if __name__ == '__main__':
    unittest.main()