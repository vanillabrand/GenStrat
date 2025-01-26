import openai
import json
import hashlib
from jsonschema import validate, ValidationError
import logging
import time
import os

class StrategyInterpreter:
    def __init__(self, api_key, cache_ttl=3600):
        self.api_key = os.getenv("OPENAI_API_KEY")
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

    def apply_defaults(self, strategy_data: dict) -> dict:
        """Applies default values for missing fields."""
        defaults = {
            "trade_parameters": {"leverage": 1, "order_type": "market", "position_size": 0.1},
            "risk_management": {"stop_loss": 5, "take_profit": 10, "trailing_stop_loss": 2},
            "conditions": {"entry": [], "exit": []},
        }
        for key, value in defaults.items():
            if key not in strategy_data:
                strategy_data[key] = value
            else:
                for sub_key, sub_value in value.items():
                    strategy_data[key].setdefault(sub_key, sub_value)
        return strategy_data

    def interpret(self, description: str) -> dict:
        """Interprets a strategy description into JSON using GPT and validates it."""
        cache_key = self._generate_cache_key(description)
        if cache_key in self.cache and not self._is_cache_expired(self.cache[cache_key]):
            self.logger.info("Returning cached result.")
            return self.cache[cache_key]["data"]

        # Call OpenAI API
        prompt = self.create_prompt(description)
        system_role = "You are an expert crypto trading assistant. Convert strategies to JSON."
        strategy_json = self.call_openai_with_fallback(prompt, system_role)

        try:
            strategy_data = json.loads(strategy_json)
            strategy_data = self.apply_defaults(strategy_data)
            
            # Validate JSON
            validate(instance=strategy_data, schema=self.schema)
            self.logger.info(f"Strategy interpreted successfully: {strategy_data}")

            # Cache the valid data
            self.cache[cache_key] = {"data": strategy_data, "timestamp": time.time()}
            return strategy_data
        except (json.JSONDecodeError, ValidationError, KeyError) as e:
            self.logger.error(f"Strategy interpretation failed: {e}")
            raise ValueError(f"Error interpreting strategy: {e}")

    def create_prompt(self, description: str) -> str:
        """Generates a detailed prompt for OpenAI."""
        return f"""
        Convert the following trading strategy description into a trading strategy in JSON format matching this schema:
        {json.dumps(self.schema, indent=2)}

        Ensure that:
        - Indicators, assets, and conditions are compatible with Backtrader, CCXT, and BitGet.
        - Choose asset pairs that are available on the exchange and market type specified. Usually this is ASSETUSDT.
        - Entry and exit conditions are fully specified and realistic. Thesed should be specified in the conditions field. Use multiples of these if you need to interpret a complicated strategy.
        - Risk management settings include stop-loss, take-profit, and trailing stop-loss. Check if the user has specified the risk level in the prompt.
        - Make sure you have enough technical information in the returned JSON to support the generation of the correct trades and parameters matching the strategy.
        - The strategy is designed for the spot, futures, or margin market type. Please specify it in the market_type field.
        - Ensure that the strategy is profitable and has an extremely high risk/reward ratio unless specificed otherwise in the prompt.
        - Ensure that the strategy is not overfit to historical data and is robust to changing market conditions.
        - Specify the timeframe for each condition in the conditions field.
        - Be aware of the limitations of the trading platform and the exchange you are using. (such as leverage limits for each market type and trading pair)
        - Write a short description of the strategy, including the rationale behind it in the strategy_rationale field.
        - Include any additional parameters or settings that are necessary for the strategy to function correctly
        - The response contains only valid JSON, no additional explanations or text. Encode strings where necessary.
        - Conditions include all relevant trading pairs, up to 30 pairs for futures and 20 pairs for spot and margin.
        - Use new and innovative strategies that are not commonly found in the market to compliment the user's request
        - Ensure the strategy takes in to consideration anti-whale and anti-bot measures to prevent manipulation of the market
        
         Strategy Description:
        {description}
        JSON:
        """

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