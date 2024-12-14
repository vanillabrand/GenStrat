import openai
import json
import hashlib
from jsonschema import validate, ValidationError
from config import OPENAI_API_KEY
import logging

class StrategyInterpreter:
    def __init__(self):
        openai.api_key = OPENAI_API_KEY
        self.schema = self._get_strategy_schema()
        self.logger = logging.getLogger(self.__class__.__name__)
        self._configure_logger()
        self.cache = {}

    def _configure_logger(self):
        """Configure logger with default settings if not already set."""
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    def _generate_cache_key(self, description: str) -> str:
        """Generate a unique cache key for the description."""
        return hashlib.md5(description.encode()).hexdigest()

    def _get_strategy_schema(self) -> dict:
        """Returns the JSON schema for strategy validation."""
        return {
            "type": "object",
            "required": ["strategy_name", "market_type", "assets", "trade_parameters", "conditions", "risk_management"],
            "properties": {
                "strategy_name": {"type": "string"},
                "market_type": {"type": "string", "enum": ["spot", "futures", "margin"]},
                "assets": {"type": "array", "items": {"type": "string"}},
                "trade_parameters": {
                    "type": "object",
                    "required": ["leverage", "order_type", "position_size"],
                    "properties": {
                        "leverage": {"type": "number"},
                        "order_type": {"type": "string"},
                        "position_size": {"type": "number"}
                    }
                },
                "conditions": {
                    "type": "object",
                    "required": ["entry", "exit"],
                    "properties": {
                        "entry": {
                            "type": "array",
                            "items": {"$ref": "#/definitions/condition"}
                        },
                        "exit": {
                            "type": "array",
                            "items": {"$ref": "#/definitions/condition"}
                        }
                    }
                },
                "risk_management": {
                    "type": "object",
                    "required": ["stop_loss", "take_profit", "trailing_stop_loss"],
                    "properties": {
                        "stop_loss": {"type": "number"},
                        "take_profit": {"type": "number"},
                        "trailing_stop_loss": {"type": "number"}
                    }
                }
            },
            "definitions": {
                "condition": {
                    "type": "object",
                    "required": ["indicator", "operator", "value", "timeframe"],
                    "properties": {
                        "indicator": {"type": "string"},
                        "operator": {"type": "string", "enum": [">", "<", "==", ">=", "<="]},
                        "value": {"type": ["string", "number"]},
                        "timeframe": {"type": "string"},
                        "indicator_parameters": {
                            "type": "object",
                            "properties": {
                                "period": {"type": "number"},
                            },
                            "additionalProperties": True
                        }
                    }
                }
            }
        }

    def call_openai_with_fallback(self, prompt: str, system_role: str) -> str:
        """Call OpenAI's API with a fallback mechanism from gpt-4 to gpt-3.5-turbo."""
        models = ["gpt-4", "gpt-3.5-turbo"]
        for model in models:
            try:
                response = openai.ChatCompletion.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_role},
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.choices[0].message.content
            except openai.error.OpenAIError as e:
                self.logger.warning(f"Model {model} failed with error: {e}")
                continue  # Try the next model in the fallback list
        raise ValueError("Both gpt-4 and gpt-3.5-turbo failed or are unavailable.")

    def interpret(self, description: str) -> dict:
        """Interprets a strategy description into JSON using GPT."""
        cache_key = self._generate_cache_key(description)
        if cache_key in self.cache:
            self.logger.info("Returning cached result.")
            return self.cache[cache_key]

        # Call OpenAI API with fallback
        prompt = self.create_prompt(description)
        system_role = "You are an expert crypto trading assistant."
        strategy_json = self.call_openai_with_fallback(prompt, system_role)
        self.logger.debug(f"Raw GPT response: {strategy_json}")

        # Parse and validate JSON
        try:
            strategy_data = json.loads(strategy_json)
            validate(instance=strategy_data, schema=self.schema)
            self.logger.info(f"Strategy interpreted successfully: {strategy_data}")
            self.cache[cache_key] = strategy_data  # Cache result
            return strategy_data
        except (json.JSONDecodeError, ValidationError) as e:
            self.logger.error(f"Error interpreting strategy: {e}")
            raise ValueError(f"Error interpreting strategy: {e}")

    def create_prompt(self, description: str) -> str:
        """Generates a prompt for GPT based on the description."""
        prompt = f"""
        You are an expert crypto trading assistant. Convert the following trading strategy description into a JSON format following this schema:

        {json.dumps(self.schema, indent=2)}

        Include all indicators (only ones available in backtrader), their parameters (only ones that are standard for ccxt and backtrader to support), assets (only ones that are available through BitGet) as trading pairs, conditions (only those supported by bitget, backtrader), risk management settings, and trade execution details (only those supported by ccxt, bitget and backtrader). 
        Response should only return the JSON with the correct parameters, nothing else. Use only crypto trading pairs paired against USDT.
        Strategy Description:
        {description}

        JSON:
        """
        return prompt

    def suggest_strategy(self, risk_level: str, market_type: str) -> dict:
        """Suggests a strategy based on risk level and market type."""
        prompt = f"""Please create a unique crypto trading strategy suitable for a '{risk_level}' risk appetite in the '{market_type}' market.
        Ensure the JSON matches this schema:
        {json.dumps(self.schema, indent=2)}

        Use indicators and conditions that can be applied by ccxt, bitget, and backtrader. Only use crypto trading pairs paired against USDT

        JSON:"""
        system_role = "You are an expert crypto trading strategist."
        strategy_json = self.call_openai_with_fallback(prompt, system_role)
        self.logger.debug(f"Raw GPT response for suggestion: {strategy_json}")

        # Parse and validate JSON
        try:
            strategy_data = json.loads(strategy_json)
            validate(instance=strategy_data, schema=self.schema)
            if strategy_data.get("market_type") != market_type:
                raise ValueError("The generated strategy's market type does not match the selected market type.")
            self.logger.info(f"Strategy suggested successfully: {strategy_data}")
            return strategy_data
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            self.logger.error(f"Error generating strategy: {e}")
            raise ValueError(f"Error generating strategy: {e}")

    def generate_trades(self, strategy_json: dict, budget: float) -> list:
        """
        Reinterprets a strategy JSON into detailed trade objects.

        Args:
            strategy_json (dict): The JSON strategy data.
            budget (float): Budget allocated for the strategy.

        Returns:
            list: A list of trade dictionaries with entry/exit conditions, risk parameters, and budget allocation.
        """
        try:
            trades = []
            total_position_size = strategy_json['trade_parameters']['position_size'] * budget

            for asset in strategy_json['assets']:
                trade = {
                    "asset": asset,
                    "entry_conditions": strategy_json['conditions']['entry'],
                    "exit_conditions": strategy_json['conditions']['exit'],
                    "budget_allocation": total_position_size / len(strategy_json['assets']),
                    "risk_management": strategy_json['risk_management'],
                    "market_type": strategy_json['market_type']
                }
                trades.append(trade)

            self.logger.info(f"Generated trades successfully: {trades}")
            return trades
        except KeyError as e:
            self.logger.error(f"Missing key in strategy JSON: {e}")
            raise ValueError(f"Invalid strategy JSON format: Missing {e}")
