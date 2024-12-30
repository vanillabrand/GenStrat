import openai
import json
import hashlib
from jsonschema import validate, ValidationError
import logging
import time


class StrategyInterpreter:
    def __init__(self, api_key, cache_ttl=3600):
        self.api_key = api_key
        self.schema = self._get_strategy_schema()
        self.logger = logging.getLogger(self.__class__.__name__)
        self._configure_logger()
        self.cache = {}
        self.cache_ttl = cache_ttl
        openai.api_key = self.api_key

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
                        "position_size": {"type": "number"},
                    },
                },
                "conditions": {
                    "type": "object",
                    "required": ["entry", "exit"],
                    "properties": {
                        "entry": {"type": "array", "items": {"$ref": "#/definitions/condition"}},
                        "exit": {"type": "array", "items": {"$ref": "#/definitions/condition"}},
                    },
                },
                "risk_management": {
                    "type": "object",
                    "required": ["stop_loss", "take_profit", "trailing_stop_loss"],
                    "properties": {
                        "stop_loss": {"type": "number"},
                        "take_profit": {"type": "number"},
                        "trailing_stop_loss": {"type": "number"},
                    },
                },
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
                            "properties": {"period": {"type": "number"}},
                            "additionalProperties": True,
                        },
                    },
                },
            },
        }

    def _is_cache_expired(self, cache_entry: dict) -> bool:
        """Checks if a cache entry has expired."""
        return (time.time() - cache_entry["timestamp"]) > self.cache_ttl

    def apply_defaults(self, strategy_data: dict) -> dict:
        """Applies default values for missing fields."""
        defaults = {
            "trade_parameters": {"leverage": 1, "order_type": "market", "position_size": 0.1},
            "risk_management": {"stop_loss": 5, "take_profit": 10, "trailing_stop_loss": 2},
        }
        for key, value in defaults.items():
            if key not in strategy_data:
                strategy_data[key] = value
            else:
                for sub_key, sub_value in value.items():
                    strategy_data[key].setdefault(sub_key, sub_value)
        return strategy_data

    def validate_completeness(self, strategy_data: dict):
        """Ensures all required conditions and fields are present."""
        required_fields = ["entry", "exit"]
        for condition in required_fields:
            if condition not in strategy_data["conditions"] or not strategy_data["conditions"][condition]:
                raise ValueError(f"Missing {condition} conditions in strategy data.")

    def interpret(self, description: str) -> dict:
        """Interprets a strategy description into JSON using GPT."""
        cache_key = self._generate_cache_key(description)
        if cache_key in self.cache:
            cache_entry = self.cache[cache_key]
            if not self._is_cache_expired(cache_entry):
                self.logger.info("Returning cached result.")
                return cache_entry["data"]
            else:
                del self.cache[cache_key]

        # Call OpenAI API with fallback
        prompt = self.create_prompt(description)
        system_role = "You are an expert crypto trading assistant."
        strategy_json = self.call_openai_with_fallback(prompt, system_role)
        self.logger.debug(f"Raw GPT response: {strategy_json}")

        # Parse and validate JSON
        try:
            strategy_data = json.loads(strategy_json)
            strategy_data = self.apply_defaults(strategy_data)
            self.validate_completeness(strategy_data)
            validate(instance=strategy_data, schema=self.schema)
            self.logger.info(f"Strategy interpreted successfully: {strategy_data}")
            self.cache[cache_key] = {"data": strategy_data, "timestamp": time.time()}
            return strategy_data
        except (json.JSONDecodeError, ValidationError, KeyError) as e:
            self.logger.error(f"Error interpreting strategy: {e}")
            raise ValueError(f"Error interpreting strategy: {e}")

    def create_prompt(self, description: str) -> str:
        """Generates a detailed prompt for OpenAI."""
        prompt = f"""
        Convert the following trading strategy description into JSON format matching this schema:
        {json.dumps(self.schema, indent=2)}

        Ensure the following:
        - Include indicators, assets, and trading pairs compatible with Backtrader, CCXT, and BitGet.
        - Specify all entry and exit conditions.
        - Risk management settings must include stop-loss, take-profit, and trailing stop-loss.
        - Ensure strategies support dynamic trade management, allowing modification, addition, and removal of trades.

        Strategy Description:
        {description}

        JSON:
        """
        return prompt

    def call_openai_with_fallback(self, prompt: str, system_role: str) -> str:
        """Call OpenAI's API with a fallback mechanism."""
        models = ["gpt-4", "gpt-3.5-turbo"]
        for model in models:
            try:
                response = openai.ChatCompletion.create(
                    model=model,
                    messages=[{"role": "system", "content": system_role}, {"role": "user", "content": prompt}],
                )
                return response.choices[0].message.content
            except openai.OpenAIError as e:
                self.logger.warning(f"Model {model} failed with error: {e}")
                continue
        raise ValueError("Both gpt-4 and gpt-3.5-turbo failed or are unavailable.")

