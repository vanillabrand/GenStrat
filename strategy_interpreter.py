import openai
import json
import hashlib
from jsonschema import validate, ValidationError
import logging
import time
import os

class StrategyInterpreter:
    """
    Interprets a natural-language trading strategy description into structured JSON.
    Uses OpenAI's API (via openai.ChatCompletion.create) with fallback, validates the returned JSON
    against a defined schema, and caches responses for a configurable time-to-live (cache_ttl).
    """

    def __init__(self, api_key: str, cache_ttl: int = 3600):
        # Read API key from environment if not provided directly
        self.api_key = os.getenv("OPENAI_API_KEY", api_key)
        self.schema = self._get_strategy_schema()
        self.logger = logging.getLogger(self.__class__.__name__)
        self._configure_logger()
        self.cache = {}  # Simple in-memory cache: {cache_key: {"data": strategy_data, "timestamp": ...}}
        self.cache_ttl = cache_ttl  # Cache time-to-live in seconds
        openai.api_key = self.api_key

    def _configure_logger(self):
        """Configure logger with default settings if not already set."""
        logging.basicConfig(level=logging.INFO, 
                            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    def _generate_cache_key(self, description: str) -> str:
        """Generate a unique cache key for the given strategy description."""
        return hashlib.md5(description.encode()).hexdigest()

    def _get_strategy_schema(self) -> dict:
        """Returns the JSON schema for strategy validation."""
        return {
            "type": "object",
            "required": ["strategy_name", "market_type", "assets", "trade_parameters", "conditions", "risk_management"],
            "properties": {
                "strategy_name": {"type": "string"},
                "strategy_rationale": {"type": "string"},
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
        """Determines if a cache entry is expired based on cache_ttl."""
        return (time.time() - cache_entry["timestamp"]) > self.cache_ttl

    def interpret(self, description: str) -> dict:
        """
        Interprets a strategy description into JSON using OpenAI and validates it.
        Checks cache first; if not cached or expired, calls OpenAI.
        """
        cache_key = self._generate_cache_key(description)
        if cache_key in self.cache and not self._is_cache_expired(self.cache[cache_key]):
            self.logger.info("Returning cached strategy interpretation result.")
            return self.cache[cache_key]["data"]

        prompt = self.create_prompt(description)
        system_role = "You are an expert crypto trading assistant. Convert strategies to JSON."
        # Use openai.ChatCompletion.create (which is awaitable) per the updated API
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_role},
                {"role": "user", "content": prompt}
            ]
        )
        try:
            strategy_json = response["choices"][0]["message"]["content"]
            strategy_data = json.loads(strategy_json)
            # Validate the returned JSON against the schema
            validate(instance=strategy_data, schema=self.schema)
            self.logger.info(f"Strategy interpreted successfully: {strategy_data}")
            # Cache the valid data
            self.cache[cache_key] = {"data": strategy_data, "timestamp": time.time()}
            return strategy_data
        except (json.JSONDecodeError, ValidationError, KeyError) as e:
            self.logger.error(f"Strategy interpretation failed: {e}")
            raise ValueError(f"Error interpreting strategy: {e}")

    def create_prompt(self, description: str) -> str:
        """Generates a detailed prompt for OpenAI based on the provided strategy description."""
        return f"""
        Convert the following trading strategy description into a trading strategy in JSON format matching this schema:
        {json.dumps(self.schema, indent=2)}

        Ensure that:
        - Indicators, assets, and conditions are compatible with Backtrader, CCXT, and BitGet.
        - Choose asset pairs that are available on the exchange and match the specified market type (e.g., ASSET/USDT).
        - Entry and exit conditions are fully specified and realistic; use multiple conditions if needed.
        - Risk management settings include stop-loss, take-profit, and trailing stop-loss.
        - Include sufficient technical details to support generating correct trades and parameters.
        - Specify the market type (spot, futures, or margin) in the 'market_type' field.
        - Ensure the strategy has a profitable and high risk/reward ratio unless stated otherwise.
        - Avoid overfitting to historical data; ensure robustness to changing market conditions.
        - Specify the timeframe for each condition in the 'conditions' field.
        - Account for limitations such as leverage limits for the chosen market and trading pair.
        - Include a short rationale in 'strategy_rationale' describing the strategy and its approach.
        - The response must contain only valid JSON—no extra commentary or text.
        - Use innovative strategies that are not common in the market.
        - Incorporate anti-whale and anti-bot measures.
        
        Strategy Description:
        {description}
        JSON:
        """
