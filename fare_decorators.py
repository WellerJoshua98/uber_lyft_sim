"""
Fare decorators using the Decorator pattern.
Allows dynamic addition of fare modifications (tips, discounts, promos, ratings)
without changing the base fare strategies.
"""
from abc import ABC, abstractmethod
from fare_calc import FareStrategy


class FareDecorator(FareStrategy, ABC):
    """
    Base decorator class that wraps a FareStrategy.
    Inherits from FareStrategy so it can be used interchangeably.
    """
    def __init__(self, wrapped_strategy: FareStrategy):
        self._wrapped_strategy = wrapped_strategy
    
    def calculate_fare(self, distance_km: float, duration_min: float) -> float:
        """Default: delegate to wrapped strategy"""
        return self._wrapped_strategy.calculate_fare(distance_km, duration_min)
    
    def get_strategy_name(self) -> str:
        """Default: delegate to wrapped strategy"""
        return self._wrapped_strategy.get_strategy_name()
    
    def get_description(self) -> str:
        """Default: delegate to wrapped strategy"""
        return self._wrapped_strategy.get_description()


class DriverRatingDecorator(FareDecorator):
    """
    Applies fare adjustment based on driver rating.
    High-rated drivers get a small premium, low-rated get a discount.
    """
    
    def __init__(self, wrapped_strategy: FareStrategy, driver_rating: float):
        super().__init__(wrapped_strategy)
        self.driver_rating = float(driver_rating)
    
    def calculate_fare(self, distance_km: float, duration_min: float) -> float:
        base_fare = self._wrapped_strategy.calculate_fare(distance_km, duration_min)
        
        # Rating-based adjustment
        # 5.0 stars: +5% premium (high demand for excellent drivers)
        # 4.5-4.9: no change
        # Below 4.5: -5% discount (incentive to use lower-rated drivers)
        
        if self.driver_rating >= 4.9:
            adjustment = 1.05  # 5% premium
        elif self.driver_rating >= 4.5:
            adjustment = 1.0   # No change
        else:
            adjustment = 0.95  # 5% discount
        
        return base_fare * adjustment
    
    def get_description(self) -> str:
        base_desc = self._wrapped_strategy.get_description()
        if self.driver_rating >= 4.9:
            return f"{base_desc} (+5% for highly-rated driver ⭐{self.driver_rating})"
        elif self.driver_rating < 4.5:
            return f"{base_desc} (-5% for lower-rated driver ⭐{self.driver_rating})"
        return base_desc


class RiderRatingDecorator(FareDecorator):
    """
    Applies fare adjustment based on rider rating.
    High-rated riders get loyalty discounts.
    """
    
    def __init__(self, wrapped_strategy: FareStrategy, rider_rating: float):
        super().__init__(wrapped_strategy)
        self.rider_rating = float(rider_rating)
    
    def calculate_fare(self, distance_km: float, duration_min: float) -> float:
        base_fare = self._wrapped_strategy.calculate_fare(distance_km, duration_min)
        
        # Loyalty discount for excellent riders
        # 5.0 stars: -3% discount (reward for being a great passenger)
        # 4.8-4.9: -2% discount
        # Below 4.8: no discount
        
        if self.rider_rating >= 5.0:
            adjustment = 0.97  # 3% discount
        elif self.rider_rating >= 4.8:
            adjustment = 0.98  # 2% discount
        else:
            adjustment = 1.0   # No discount
        
        return base_fare * adjustment
    
    def get_description(self) -> str:
        base_desc = self._wrapped_strategy.get_description()
        if self.rider_rating >= 5.0:
            return f"{base_desc} (-3% loyalty discount for 5⭐ rider)"
        elif self.rider_rating >= 4.8:
            return f"{base_desc} (-2% loyalty discount for {self.rider_rating}⭐ rider)"
        return base_desc


class TipDecorator(FareDecorator):
    """Adds a percentage tip to the fare"""
    
    def __init__(self, wrapped_strategy: FareStrategy, tip_percentage: float = 15.0):
        super().__init__(wrapped_strategy)
        self.tip_percentage = tip_percentage
    
    def calculate_fare(self, distance_km: float, duration_min: float) -> float:
        base_fare = self._wrapped_strategy.calculate_fare(distance_km, duration_min)
        tip_amount = base_fare * (self.tip_percentage / 100)
        return base_fare + tip_amount
    
    def get_description(self) -> str:
        base_desc = self._wrapped_strategy.get_description()
        return f"{base_desc} + {self.tip_percentage}% tip"


class DiscountDecorator(FareDecorator):
    """Applies a percentage discount to the fare"""
    
    def __init__(self, wrapped_strategy: FareStrategy, discount_percentage: float = 10.0):
        super().__init__(wrapped_strategy)
        self.discount_percentage = discount_percentage
    
    def calculate_fare(self, distance_km: float, duration_min: float) -> float:
        base_fare = self._wrapped_strategy.calculate_fare(distance_km, duration_min)
        discount_amount = base_fare * (self.discount_percentage / 100)
        return base_fare - discount_amount
    
    def get_description(self) -> str:
        base_desc = self._wrapped_strategy.get_description()
        return f"{base_desc} - {self.discount_percentage}% discount"


class PromoCodeDecorator(FareDecorator):
    """Applies a fixed amount discount via promo code"""
    
    def __init__(self, wrapped_strategy: FareStrategy, promo_code: str, discount_amount: float):
        super().__init__(wrapped_strategy)
        self.promo_code = promo_code
        self.discount_amount = discount_amount
    
    def calculate_fare(self, distance_km: float, duration_min: float) -> float:
        base_fare = self._wrapped_strategy.calculate_fare(distance_km, duration_min)
        final_fare = max(base_fare - self.discount_amount, 0)  # Don't go negative
        return final_fare
    
    def get_description(self) -> str:
        base_desc = self._wrapped_strategy.get_description()
        return f"{base_desc} - ${self.discount_amount:.2f} off (Promo: {self.promo_code})"


class FlatFeeDecorator(FareDecorator):
    """Adds a flat fee (e.g., airport fee, toll)"""
    
    def __init__(self, wrapped_strategy: FareStrategy, fee_name: str, fee_amount: float):
        super().__init__(wrapped_strategy)
        self.fee_name = fee_name
        self.fee_amount = fee_amount
    
    def calculate_fare(self, distance_km: float, duration_min: float) -> float:
        base_fare = self._wrapped_strategy.calculate_fare(distance_km, duration_min)
        return base_fare + self.fee_amount
    
    def get_description(self) -> str:
        base_desc = self._wrapped_strategy.get_description()
        return f"{base_desc} + ${self.fee_amount:.2f} {self.fee_name}"