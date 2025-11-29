"""
Fare calculation strategies using the Strategy pattern.
Different fare calculation algorithms can be swapped at runtime.
"""
from abc import ABC, abstractmethod
from datetime import datetime


class FareStrategy(ABC):
    """Abstract strategy for fare calculation"""
    
    @abstractmethod
    def calculate_fare(self, distance_km: float, duration_min: float) -> float:
        """Calculate fare based on distance and duration"""
        pass
    
    @abstractmethod
    def get_strategy_name(self) -> str:
        """Return the name of this strategy"""
        pass
    
    def get_description(self) -> str:
        """Return a description of this strategy"""
        return f"{self.get_strategy_name()} fare calculation"


class StandardFareStrategy(FareStrategy):
    """Standard fare calculation - base rates"""
    
    BASE_FARE = 2.50
    PER_KM_RATE = 1.50
    PER_MINUTE_RATE = 0.30
    MIN_FARE = 5.00
    
    def calculate_fare(self, distance_km: float, duration_min: float) -> float:
        """Calculate standard fare"""
        fare = (self.BASE_FARE + 
                (distance_km * self.PER_KM_RATE) + 
                (duration_min * self.PER_MINUTE_RATE))
        return max(fare, self.MIN_FARE)
    
    def get_strategy_name(self) -> str:
        return "Standard"


class SurgeFareStrategy(FareStrategy):
    """Surge pricing - multiplier applied during high demand"""
    
    BASE_FARE = 2.50
    PER_KM_RATE = 1.50
    PER_MINUTE_RATE = 0.30
    MIN_FARE = 5.00
    SURGE_MULTIPLIER = 1.3  # 80% increase
    
    def calculate_fare(self, distance_km: float, duration_min: float) -> float:
        """Calculate surge fare with multiplier"""
        base_fare = (self.BASE_FARE + 
                    (distance_km * self.PER_KM_RATE) + 
                    (duration_min * self.PER_MINUTE_RATE))
        fare = base_fare * self.SURGE_MULTIPLIER
        return max(fare, self.MIN_FARE * self.SURGE_MULTIPLIER)
    
    def get_strategy_name(self) -> str:
        return "Surge"
    
    def get_description(self) -> str:
        return f"Surge pricing ({int((self.SURGE_MULTIPLIER - 1) * 100)}% increase due to high demand)"


class PremiumFareStrategy(FareStrategy):
    """Premium service - luxury vehicles with higher rates"""
    
    BASE_FARE = 5.00
    PER_KM_RATE = 2.50
    PER_MINUTE_RATE = 0.50
    MIN_FARE = 10.00
    
    def calculate_fare(self, distance_km: float, duration_min: float) -> float:
        """Calculate premium fare"""
        fare = (self.BASE_FARE + 
                (distance_km * self.PER_KM_RATE) + 
                (duration_min * self.PER_MINUTE_RATE))
        return max(fare, self.MIN_FARE)
    
    def get_strategy_name(self) -> str:
        return "Premium"
    
    def get_description(self) -> str:
        return "Premium service with luxury vehicles and priority pickup"


class FareStrategyFactory:
    """Factory pattern for creating fare strategies"""
    
    _strategies = {
        "Standard": StandardFareStrategy,
        "Surge": SurgeFareStrategy,
        "Premium": PremiumFareStrategy
    }
    
    @classmethod
    def create_strategy(cls, strategy_name: str) -> FareStrategy:
        """Create a fare strategy by name"""
        strategy_class = cls._strategies.get(strategy_name)
        if not strategy_class:
            raise ValueError(f"Unknown strategy: {strategy_name}. "
                           f"Available: {list(cls._strategies.keys())}")
        return strategy_class()
    
    @classmethod
    def get_available_strategies(cls) -> list:
        """Get list of available strategy names"""
        return list(cls._strategies.keys())
    
    @classmethod
    def register_strategy(cls, name: str, strategy_class: type) -> None:
        """Register a new strategy type (extensibility)"""
        cls._strategies[name] = strategy_class