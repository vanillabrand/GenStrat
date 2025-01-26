class StrategyError(Exception):
    """Base class for Strategy exceptions"""
    pass

class StrategyValidationError(StrategyError):
    """Raised when strategy validation fails"""
    pass

class StrategyNotFoundError(StrategyError):
    """Raised when a strategy cannot be found"""
    pass

class StrategyStorageError(StrategyError):
    """Raised when there's an error storing/retrieving strategy"""
    pass
